import copy
import math

import cv2
import numpy as np
from PIL import Image
from imutils import perspective
from scipy.spatial import distance as dist

from backend.utils import rect_to_polar, get_timestamp, midpoint

__image_path = None
__original_image = None
__config_image = None
__contour_boxes = []
__original_circumferences = []  # keeps all the circumferences originally found
__circumferences = []  # list of tuples: (contour, (centroidX, centroidY))
__pixels_per_metric = None
__circumferences_data = []  # list of tuples: (rs, thetas, avg_diameter)
__output_image = None


def get_image_path():
    return __image_path


def get_config_image():
    return __config_image


def get_number_original_circumferences():
    return len(__original_circumferences)


def do_pre_processing(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # OPTION 1
    gray = cv2.GaussianBlur(gray, ksize=(5, 5), sigmaX=0)

    # OPTION 2
    # smooth out any background noise and preserve edges
    # gray = cv2.bilateralFilter(gray, d=5, sigmaColor=75, sigmaSpace=50)

    # perform edge detection, then perform a dilation + erosion to close gaps in between object edges
    edged = cv2.Canny(gray, threshold1=0, threshold2=60)
    edged = cv2.dilate(edged, kernel=None, iterations=1)
    edged = cv2.erode(edged, kernel=None, iterations=1)

    return edged


def process_image(image_path):
    """
    Retrieves contours of circumferences and other (reference) objects.

    :param image_path: path to source image in filesystem.
    :return: number of circumferences found
    """
    global __image_path, __original_image, __config_image, __contour_boxes, __original_circumferences, __circumferences

    # load the image
    __original_image = cv2.imread(image_path)
    if __original_image is None:
        return None

    # save image path
    __image_path = image_path

    # the image we'll display in the configuration screen, with all the detected circumferences
    __config_image = __original_image.copy()

    # reset boxes and circumferences
    __contour_boxes.clear()
    __original_circumferences.clear()
    __circumferences.clear()

    # Reduce background noise and apply canny edge detection
    temp_image = do_pre_processing(__original_image)

    # find contours
    _, cnts, _ = cv2.findContours(image=temp_image, mode=cv2.RETR_CCOMP, method=cv2.CHAIN_APPROX_NONE)

    for c in cnts:
        area = cv2.contourArea(c)

        # ignore small contours
        if area < 10000:
            continue

        # compute the rotated bounding box of the contour
        box = cv2.minAreaRect(c)
        box = cv2.boxPoints(box)
        box = np.array(box, dtype="int")

        # order the points in the contour such that they appear
        # in top-left, top-right, bottom-right, and bottom-left
        # order, then draw the outline of the rotated bounding
        # box
        box = perspective.order_points(box)

        # save these boxes so we can browse them in the GUI
        __contour_boxes.append(box)

        perimeter = cv2.arcLength(c, closed=True)
        approx = cv2.approxPolyDP(c, epsilon=0.01 * perimeter, closed=True)

        # Look for circular objects
        if len(approx) > 10 and len(approx) < 20:
            # filter with contour properties

            # Bounding rectangle
            x, y, w, h = cv2.boundingRect(c)

            # aspect ratio
            aspect_ratio = float(w) / h

            # solidity
            hull = cv2.convexHull(c)
            hull_area = cv2.contourArea(hull)
            solidity = float(area) / hull_area

            # valid properties
            size_ok = w > 25 and h > 25
            solidity_ok = solidity > 0.9
            aspect_ratio_ok = aspect_ratio >= 0.8 and aspect_ratio <= 1.2

            if size_ok and solidity_ok and aspect_ratio_ok:
                # get centroid
                M = cv2.moments(c)
                (cx, cy) = int(M['m10'] / M['m00']), int(M['m01'] / M['m00'])

                # Save circumference and centroid
                circumference = (c, (cx, cy))
                __circumferences.append(circumference)

                # Draw circumferences to display all of them in the configuration screen
                cv2.drawContours(__config_image, [c], 0, color=(0, 255, 0), thickness=5)

    # convert config image to pil
    __config_image = convert_cv_to_pil(__config_image)

    # keep a copy of the originals before selecting finals
    if len(__circumferences) > 2:
        __original_circumferences = copy.copy(__circumferences)

    return len(__circumferences)


def render_all_circumferences():
    circumference_images = []

    for circumference in __original_circumferences:
        cnt = circumference[0]
        circ_image = __original_image.copy()

        cv2.drawContours(circ_image, [cnt], 0, color=(0, 255, 0), thickness=5)

        # convert to PIL and add to result
        circumference_images.append(convert_cv_to_pil(circ_image))

    return circumference_images


def set_final_circumferences(selected):
    global __circumferences

    final_circumferences = []

    for i, circumference in enumerate(__original_circumferences):
        if i in selected:
            final_circumferences.append(circumference)

    __circumferences = final_circumferences


def render_boxes():
    """
    Generates images of each contour's bounding box (with horizontal and vertical bisections)

    :return: a list of bounding boxes in the following format: { "horizontal": (TkImage, width), "vertical": (TkImage, height) }
    """
    global __original_image, __contour_boxes

    boxes = []

    for box in __contour_boxes:

        # 1st of 2 output images: horizontal and vertical bisections
        orig_horizontal_line = __original_image.copy()

        # draw the actual boxes
        cv2.drawContours(orig_horizontal_line, [box.astype("int")], -1, color=(0, 255, 0), thickness=5)

        # loop over the original points and draw them
        for (x, y) in box:
            cv2.circle(orig_horizontal_line, (int(x), int(y)), 5, (0, 0, 255), -1)

        # unpack the ordered bounding box, then compute the midpoint
        # between the top-left and top-right coordinates, followed by
        # the midpoint between bottom-left and bottom-right coordinates
        (tl, tr, br, bl) = box

        # Midpoints
        # Forms vertical bisection
        (tl_tr_x, tl_tr_y) = midpoint(tl, tr)  # top-left and top-right
        (bl_br_x, bl_br_y) = midpoint(bl, br)  # bottom-left and bottom-right

        # Forms horizontal bisection
        (tl_bl_x, tl_bl_y) = midpoint(tl, bl)  # top-left and bottom-left
        (tr_br_x, tr_br_y) = midpoint(tr, br)  # top-right and bottom-right

        # 2nd output image; Here is where the images deviate
        orig_vertical_line = orig_horizontal_line.copy()

        # draw the midpoints on the image
        cv2.circle(orig_vertical_line, (int(tl_tr_x), int(tl_tr_y)), 5, (255, 0, 0), -1)
        cv2.circle(orig_vertical_line, (int(bl_br_x), int(bl_br_y)), 5, (255, 0, 0), -1)
        cv2.circle(orig_horizontal_line, (int(tl_bl_x), int(tl_bl_y)), 5, (255, 0, 0), -1)
        cv2.circle(orig_horizontal_line, (int(tr_br_x), int(tr_br_y)), 5, (255, 0, 0), -1)

        # draw lines between the midpoints
        cv2.line(orig_vertical_line, (int(tl_tr_x), int(tl_tr_y)), (int(bl_br_x), int(bl_br_y)), (255, 0, 255), thickness=5)
        cv2.line(orig_horizontal_line, (int(tl_bl_x), int(tl_bl_y)), (int(tr_br_x), int(tr_br_y)), (255, 0, 255), thickness=5)

        # draw text on midpoint of lines
        # vertical
        (m_vertical_x, m_vertical_y) = midpoint((tl_tr_x, tl_tr_y), (bl_br_x, bl_br_y))
        cv2.putText(orig_vertical_line, "? cm", (int(m_vertical_x + 10), int(m_vertical_y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 0, 255), thickness=3)
        # horizontal
        (m_horizontal_x, m_horizontal_y) = midpoint((tl_bl_x, tl_bl_y), (tr_br_x, tr_br_y))
        cv2.putText(orig_horizontal_line, "? cm", (int(m_horizontal_x), int(m_horizontal_y + 40)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 0, 255), thickness=3)

        # calculate the box's width and height
        box_height = dist.euclidean((tl_tr_x, tl_tr_y), (bl_br_x, bl_br_y))
        box_width = dist.euclidean((tl_bl_x, tl_bl_y), (tr_br_x, tr_br_y))

        contour_box = {
            "horizontal": (convert_cv_to_pil(orig_horizontal_line), box_width),
            "vertical": (convert_cv_to_pil(orig_vertical_line), box_height)
        }

        boxes.append(contour_box)

    return boxes


def set_pixels_per_metric(value):
    global __pixels_per_metric
    __pixels_per_metric = value


def sort_circumferences():
    # get a reference of each circumference tuple (contour, centroid, hull)
    circumference_1 = __circumferences[0]
    circumference_2 = __circumferences[1]

    # find out which contour is bigger
    area_1 = len(circumference_1[0])
    area_2 = len(circumference_2[0])

    # outer circumference should come first
    if area_2 > area_1:
        __circumferences.reverse()
        print("circumferences order reversed")


# TODO finish this test
def contour_to_approx(contour):
    perimeter = cv2.arcLength(contour, closed=True)
    return cv2.approxPolyDP(contour, epsilon=0.0001 * perimeter, closed=True)


def circumferences_to_polar_and_avg_diameter():
    global __pixels_per_metric, __circumferences_data

    # sort circumferences; Outer always first
    sort_circumferences()

    # 2 rows for each circumference: contains (rs, thetas, avg diameter)
    __circumferences_data.clear()

    for circumference in __circumferences:
        (contour, centroid) = circumference
        temp_r = []
        temp_theta = []
        temp_diameters = []

        # temp_contour = cv2.convexHull(contour)
        temp_contour = contour_to_approx(contour)

        for points in contour:
        # for points in temp_contour:
            for inner in points:
                (r, theta) = rect_to_polar(point=inner, center=centroid, inverted_y=True)
                scaled_r = r / __pixels_per_metric

                # save diameter for average
                temp_diameters.append(scaled_r * 2.0)

                # save radius
                temp_r.append(round(scaled_r, 2))
                # save theta
                temp_theta.append(round(math.degrees(theta), 2))

        # calculate average diameter
        temp_average_diameter = np.round(np.mean(temp_diameters), 2)

        # save
        __circumferences_data.append((temp_r, temp_theta, temp_average_diameter))

    return __circumferences_data


def get_slice_roi():
    global __output_image

    # make sure outer is first
    sort_circumferences()

    # a copy of the original image
    temp = __original_image.copy()

    # red and blue to match matplotlib
    # colors = ((179, 115, 24), (15, 132, 255))
    colors = ((0, 0, 255), (179, 115, 24))

    # outline the circumferences
    for ((contour, centroid), color) in zip(__circumferences, colors):
        temp = cv2.drawContours(temp, [contour], 0, color=color, thickness=5)

    contour, centroid = __circumferences[0]  # outer circumference

    # extract region of interest from original image
    x, y, w, h = cv2.boundingRect(contour)
    roi = temp[y:y+h, x:x+w]

    __output_image = convert_cv_to_pil(roi)

    return __output_image


def generate_text_file(file_path):
    global __circumferences, __circumferences_data

    # get point of reference to express centroid as a rectangular coordinate
    contour, _ = __circumferences[0]  # outer

    # leftmost point gives x0
    leftmost = tuple(contour[contour[:, :, 0].argmin()][0])
    # bottommost point gives y0
    bottommost = tuple(contour[contour[:, :, 1].argmax()][0])

    # origin
    (x0, y0) = leftmost[0], bottommost[1]

    try:
        f = open(file_path, "w+")
        f.write("Image processed: %s\n" % __image_path)
        f.write("\n")
        f.write(get_timestamp())
        f.write("\n")

        tags = ("Outer Circumference", "Inner Circumference")
        for ((rs, thetas, avg_diameter), (contour, centroid), tag) in zip(__circumferences_data, __circumferences, tags):

            # Write circumference tag
            f.write("*%s*\n" % tag)

            # write polar coords
            f.write("Polar coordinates:\n")
            for (r, theta) in zip(rs, thetas):
                f.write(" (%s, %s) " % (r, theta))
            f.write("\n")

            # write centroid
            # coordinates in original image
            (cx, cy) = centroid

            # translate in relation to calculated origin, and scaled with pixels-per-metric
            cx_final = round(abs(cx - x0) / __pixels_per_metric, 2)
            cy_final = round(abs(cy - y0) / __pixels_per_metric, 2)

            f.write("Centroid: (%s, %s)" % (cx_final, cy_final))
            f.write("\n")

            # write average diameter
            f.write("Average Diameter: %s" % avg_diameter)
            f.write("\n")

            f.write("\n")

        f.close()
        return True

    except IOError as e:
        print("I/O error({0}): {1}".format(e.errno, e.strerror))
        return False


def reset_bsc_backend():
    global __image_path, __original_image, __config_image, __pixels_per_metric, __contour_boxes,\
        __original_circumferences, __circumferences, __circumferences_data, __output_image

    __image_path = None
    __original_image = None
    __config_image = None
    __contour_boxes.clear()
    __original_circumferences.clear()
    __circumferences.clear()
    __pixels_per_metric = None
    __circumferences_data.clear()
    __output_image = None


def convert_cv_to_pil(image):
    # swap color channels: BGR -> RGB
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # convert the image to PIL format
    return Image.fromarray(image)


if __name__ == "__main__":
    print(process_image("C:/Users/arosa/PycharmProjects/BambooScanner/test3a.jpg"))
    set_pixels_per_metric(5.0)
    # print(circumferences_to_polar())
    # render_all_circumferences()
    # generate_text_file("C:/Users/arosa/PycharmProjects/BambooScanner/BSC_test.txt")
