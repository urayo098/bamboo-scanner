import queue
from tkinter import *
from tkinter import messagebox

from backend.bpc import saved_measurement
from backend.bpc_threading import *
from gui.widgets.custom import HorizontalTable, YellowButton, GreenButton, VerticalTable
from gui.widgets.helpers import make_rows_responsive, make_columns_responsive


class MeasureBPC(Frame):

    def __init__(self, parent, controller):
        Frame.__init__(self, parent)
        self.controller = controller
        self.title = "Live Sensor Readings (cm)"
        self.initialize_widgets()
        self.bind("<<ShowFrame>>", self.on_show_frame)
        self.bind("<<LeaveFrame>>", self.on_leave_frame)

        # Queue where live feed thread writes data
        self.queue = queue.LifoQueue()

    def add_to_queue(self, data):
        self.queue.put(data)

    def initialize_widgets(self):
        # Watchers
        # Update captured count
        self.count_str = StringVar()
        self.count_number = IntVar()
        self.count_number.trace("w", self.update_count_label)

        # Status message
        self.status_var = StringVar()
        self.status_message = Label(self, textvariable=self.status_var, font=self.controller.header_font, relief=GROOVE,
                                    padx=10, pady=10)
        self.status_message.grid(row=0, column=0, sticky=EW, padx=40, pady=20)

        # Sensor Z
        # self.z_value = StringVar()
        # self.z_label = Label(self, textvariable=self.z_value, font=self.controller.important_font)
        # self.z_label.grid(row=1, column=0, sticky=S)

        # Table headers
        top_headers = ["Sensor #", "Current\nreading", "Last\ncaptured\nvalue", "Last\ndeviation"]
        self.table_headers = VerticalTable(self, rows=1, columns=len(top_headers))
        self.table_headers.update_cells(top_headers)
        self.table_headers.grid(row=1, column=0, sticky=S)

        # Object containing the table's data
        self.table_data = [[], [], []]
        # column indexes
        self.live_column = 0
        self.captured_column = 1
        self.deviation_column = 2

        # Sensor Data: current readings, last captured, and deviation info
        sensor_headers = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "Sensor Z"]
        self.table = HorizontalTable(self, rows=len(sensor_headers), columns=3, header_values=sensor_headers)
        self.table.grid(row=2, column=0, rowspan=2, sticky=N)

        # calibrate button
        self.calibrate_button = GreenButton(self, text="Calibrate Sensors", command=self.calibrate)
        self.calibrate_button.grid(row=0, column=1, pady=20)

        # captured count
        self.captured_count = Label(self, textvariable=self.count_str, font=self.controller.bold_font)
        self.captured_count.grid(row=2, column=1, sticky=S, pady=10)

        # capture button
        self.capture_button = YellowButton(self, text="Capture Measurements", command=self.capture)
        self.capture_button.grid(row=3, column=1, sticky=N)

        # view results button
        self.results_button = GreenButton(self, text="View Results", command=self.view_results,
                                          image=self.controller.arrow_right, compound=RIGHT)
        self.results_button.grid(row=4, column=1, sticky=SE, padx=20, pady=20)

        make_rows_responsive(self)
        make_columns_responsive(self)

    def on_show_frame(self, event=None):
        # TODO get count from function
        self.count_number.set(len(saved_measurement))

        # clear live readings from table
        self.table_data[self.live_column].clear()

        # Controls update callback
        self.do_update = True
        # Flag to only update buttons and message when necessary
        self.busy_message_set = False

        # start live GUI
        self.update_live_gui()
        # Open port and start reading
        self.run_live_thread()

    def run_live_thread(self):
        self.live_thread = threading.Thread(target=get_live_sensors, name="live_sensors",
                                            args=(self,))
        self.live_thread.start()

    def update_live_gui(self):
        # No Arduino found alert
        if no_arduino.is_set():
            no_arduino.clear()

            result = messagebox.askretrycancel("Error opening serial port",
                                               "Make sure the Arduino is properly connected, and try again.",
                                               icon="error")
            # Retry
            if result:
                # open new thread
                self.run_live_thread()
            else:
                self.controller.show_frame("ConfigBPC")
                return

        # Arduino disconnected alert
        if disconnected.is_set():
            disconnected.clear()

            result = messagebox.askretrycancel("Error reading from Arduino",
                                               "Make sure the Arduino is properly connected, and try again.",
                                               icon="error")
            # Retry
            if result:
                # open new thread
                self.run_live_thread()
            else:
                self.controller.show_frame("ConfigBPC")
                return

        # Capturing data
        if capture_now.is_set():
            # only set message once
            if not self.busy_message_set:
                # Show status message
                self.status_var.set("Capturing data...")

                # Disable buttons
                self.disable_buttons()

                # message has been set
                self.busy_message_set = True

            # when data has been captured
            if capture_done.is_set():
                last_captured = saved_measurement[len(saved_measurement) - 1]

                # store last captured in table data object
                self.table_data[self.captured_column] = last_captured

                # update table with new data
                self.table.update_cells(self.table_data)

                # clear flags
                capture_done.clear()
                capture_now.clear()

        # Calibrating sensors
        elif calibrate_now.is_set():
            # only set message once
            if not self.busy_message_set:
                # Show status message
                self.status_var.set("Calibrating sensors...")

                # Disable buttons
                self.disable_buttons()

                # message has been set
                self.busy_message_set = True

            # when calibration is done
            if calibration_done.is_set():
                deviations = []

                # exclude the last one; it's the ultrasonic
                for i in range(len(sensorArray) - 1):
                    # IR sensor deviation angle
                    deviations.append(sensorArray[i].devAngle)

                # ultrasonic sensor
                ultrasonic = sensorArray[len(sensorArray) - 1]
                deviations.append(ultrasonic.factor)

                # store deviations in table data object
                self.table_data[self.deviation_column] = deviations

                # update table with new data
                self.table.update_cells(self.table_data)

                # clear flags
                calibration_done.clear()
                calibrate_now.clear()

        # Update live feed
        elif reading_sensors.is_set() and not capture_now.is_set():
            try:
                while True:
                    data = self.queue.get_nowait()

                    # store readings in table data object
                    self.table_data[self.live_column] = data

                    # Update table with new sensor data
                    self.table.update_cells(self.table_data)
                    # self.z_value.set("Z = " + data[len(data) - 1] + " cm")

                    # only set message once
                    if self.busy_message_set:
                        # Ready to capture or calibrate
                        self.status_var.set("Ready!")

                        # Restore buttons
                        self.restore_buttons()

                        # no longer busy
                        self.busy_message_set = False

                    self.update_idletasks()
            except queue.Empty:
                pass

        # Sensors are still initializing
        elif not reading_sensors.is_set() and self.do_update and not self.busy_message_set:
            # Show loading message
            self.status_var.set("Connecting to sensors...")

            # Disable buttons
            self.disable_buttons()

            # message has been set
            self.busy_message_set = True

        # Keep updating until we leave this frame
        if self.do_update:
            self.after(100, self.update_live_gui)

    def restore_buttons(self):
        self.calibrate_button.configure(state=NORMAL, cursor="hand2")
        self.capture_button.configure(state=NORMAL, cursor="hand2")

        # only enable view results if there are any
        if self.count_number.get():
            self.results_button.configure(state=NORMAL, cursor="hand2")

        # leave it disabled, but with a different cursor
        else:
            self.results_button.configure(state=DISABLED, cursor="arrow")

    def disable_buttons(self):
        self.calibrate_button.configure(state=DISABLED, cursor="wait")
        self.capture_button.configure(state=DISABLED, cursor="wait")
        self.results_button.configure(state=DISABLED, cursor="wait")

    def on_leave_frame(self, event=None):
        # stop live feed and close serial port
        kill_thread.set()
        reading_sensors.clear()
        self.do_update = False

    def calibrate(self):
        # only one at a time
        if not calibrate_now.is_set():
            # Let the worker thread handle it
            calibrate_now.set()

    def capture(self):
        # only one at a time
        if not capture_now.is_set():
            # Let the worker thread handle it
            capture_now.set()

            # update captured count label
            self.count_number.set(self.count_number.get() + 1)

    def update_count_label(self, *args):
        self.count_str.set(str(self.count_number.get()) + " measurements captured")

    def view_results(self):
        self.controller.show_frame("ResultsBPC")

    def reset(self):
        # reset captured count
        self.count_number.set(0)
