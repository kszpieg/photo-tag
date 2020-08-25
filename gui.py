from datetime import datetime

import cv2
import wx
import glob
import os
import time
import json
import shutil
from pathlib import Path
from image_converter import wxBitmapFromCvImage
from pubsub import pub
from wx.lib.masked import numctrl


def optimize_bitmap_person(bitmap):
    screensize = wx.DisplaySize()
    w = screensize[0] * 0.35
    h = screensize[1] * 0.64
    if bitmap.GetWidth() > w:
        image = bitmap.ConvertToImage()
        calculated_height = (bitmap.GetHeight() * w) / bitmap.GetWidth()
        bitmap = wx.Bitmap(image.Scale(w, calculated_height))
    if bitmap.GetHeight() > h:
        image = bitmap.ConvertToImage()
        calculated_width = (bitmap.GetWidth() * h) / bitmap.GetHeight()
        bitmap = wx.Bitmap(image.Scale(calculated_width, h))
    return bitmap


def optimize_cv_image(image):
    h, w = image.shape[:2]
    screensize = wx.DisplaySize()
    display_w = int(screensize[0] * 0.35)
    display_h = int(screensize[1] * 0.64)
    if w > display_w:
        calculated_height = int((h * display_w) / w)
        resized_img = cv2.resize(image, (display_w, calculated_height))
        image = resized_img
    if h > display_h:
        calculated_width = int((w * display_h) / h)
        resized_img = cv2.resize(image, (calculated_width, display_h))
        image = resized_img
    return image


class AppPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_image_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_objects_sizer = wx.BoxSizer(wx.HORIZONTAL)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.current_folder_path = ""
        self.current_file_path = ""
        self.row_obj_dict = {}
        self.file_names = []
        self.selection = 0
        self.label_photo = ""
        self.created_tags_count = 0
        self.ix = -1
        self.iy = -1
        self.iw = -1
        self.ih = -1
        self.drawing = False
        self.second_window_closed = True
        self.tags_data = {}
        self.tag_number = 0
        self.all_tags_data = {}
        self.slider_value = 5
        self.objects_dict = {}
        self.is_list_ctrl_empty = True

        pub.subscribe(self.tag_details_listener, "tag_details_listener")
        pub.subscribe(self.close_tag_details_window, "close_tag_details_window")
        pub.subscribe(self.update_objects_list, "update_objects_list")

        self.list_ctrl = wx.ListCtrl(
            self, size=(650, 150),
            style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl.InsertColumn(0, "File name", width=250)
        self.list_ctrl.InsertColumn(1, "Date", width=150)
        self.list_ctrl.InsertColumn(2, "File extension", width=100)
        self.list_ctrl.InsertColumn(3, "Size", width=100)
        left_sizer.Add(self.list_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        btn_data = [("Select image", btn_main_sizer, self.select_photo),
                    ("Generate album", btn_main_sizer, self.open_generator_window)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)
        left_sizer.Add(btn_main_sizer, 0, wx.CENTER)
        self.list_ctrl_tags = wx.ListCtrl(
            self, size=(650, 150),
            style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl_tags.InsertColumn(0, "Tag\'s name", width=280)
        self.list_ctrl_tags.InsertColumn(1, "Tag\'s rate", width=100)
        left_sizer.Add(self.list_ctrl_tags, 0, wx.ALL | wx.EXPAND, 5)
        btn_data_objects = [("All objects list", btn_objects_sizer, self.all_objects_window),
                            ("Delete selected tag", btn_objects_sizer, self.delete_selected_tag),
                            ("Show selected tag", btn_objects_sizer, self.show_selected_tag)]
        for data in btn_data_objects:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)
        left_sizer.Add(btn_objects_sizer, 0, wx.CENTER)

        bmp_image = wx.Image(wx.EXPAND, wx.EXPAND)
        self.image_ctrl = wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(bmp_image))
        right_sizer.Add(self.image_ctrl, 0, wx.ALL | wx.ALIGN_CENTER | wx.ALIGN_TOP, 5)

        self.image_label = wx.StaticText(self, label="")
        right_sizer.Add(self.image_label, 0, wx.ALL | wx.CENTER, 5)

        self.created_tags_info_label = wx.StaticText(self, label="")
        right_sizer.Add(self.created_tags_info_label, 0, wx.ALL | wx.CENTER, 5)

        btn_data_under_photo = [("Previous image", btn_image_sizer, self.previous_image),
                                ("Make tag", btn_image_sizer, self.tag_persons),
                                ("Save tags", btn_image_sizer, self.save_tags_on_the_photo),
                                ("Next image", btn_image_sizer, self.next_image)]
        for data in btn_data_under_photo:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)
        right_sizer.Add(btn_image_sizer, 0, wx.CENTER)

        msg_photo_rate = "Photo\'s rate:"
        photo_rate_text = wx.StaticText(self, label=msg_photo_rate)

        self.photo_slider = wx.Slider(self, value=self.slider_value, minValue=0, maxValue=10, size=(350, 50),
                                      style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.photo_slider.Bind(wx.EVT_SLIDER, self.on_photo_slider_scroll)
        right_sizer.Add(photo_rate_text, 0, wx.CENTER, border=15)
        right_sizer.Add(self.photo_slider, 0, wx.CENTER, border=20)

        main_sizer.Add(left_sizer, wx.ALIGN_LEFT, 5)
        main_sizer.Add(right_sizer, wx.ALIGN_RIGHT, 5)
        self.SetSizer(main_sizer)

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def on_photo_slider_scroll(self, event):
        obj = event.GetEventObject()
        self.slider_value = obj.GetValue()
        font = self.GetFont()
        font.SetPointSize(self.photo_slider.GetValue())

    def update_files_listing(self, folder_path):
        self.current_folder_path = folder_path
        self.list_ctrl.DeleteAllItems()
        self.file_names.clear()

        photos = glob.glob(folder_path + "/*.jpg")
        photo_objects = []
        index = 0
        for photo in photos:
            photo_object = cv2.imread(photo)
            self.list_ctrl.InsertItem(index, Path(photo).stem)
            self.file_names.append(Path(photo).stem + Path(photo).suffix)
            if self.file_names[index] in self.all_tags_data:
                self.list_ctrl.SetItemTextColour(index, wx.Colour(0, 255, 0))
            self.list_ctrl.SetItem(index, 1, str(time.strftime('%d/%m/%Y', time.gmtime(os.path.getmtime(photo)))))
            self.list_ctrl.SetItem(index, 2, Path(photo).suffix)
            self.list_ctrl.SetItem(index, 3, str(os.path.getsize(photo)) + " B")
            photo_objects.append(photo_object)
            self.row_obj_dict[index] = photo_object
            index += 1
        self.is_list_ctrl_empty = False

    def update_tags_listing(self, file_name):
        self.list_ctrl_tags.ClearAll()
        self.list_ctrl_tags.InsertColumn(0, "Tag\'s name", width=280)
        self.list_ctrl_tags.InsertColumn(1, "Tag\'s rate", width=100)
        if file_name in self.all_tags_data:
            for tag in self.all_tags_data[file_name]['tags'].items():
                self.list_ctrl_tags.InsertItem(int(tag[0]), tag[1]['label'])
                self.list_ctrl_tags.SetItem(int(tag[0]), 1, str(tag[1]['rate']))

    def load_photo(self, photo):
        converted_image = wxBitmapFromCvImage(photo)
        bitmap = optimize_bitmap_person(wx.Bitmap(converted_image))
        self.image_ctrl.SetBitmap(bitmap)
        self.image_label.SetLabelText(self.file_names[self.selection])
        if self.file_names[self.selection] in self.all_tags_data:
            self.photo_slider.SetValue(self.all_tags_data[self.file_names[self.selection]]['photo_rate'])
            self.slider_value = self.photo_slider.GetValue()
        else:
            self.photo_slider.SetValue(5)
            self.slider_value = self.photo_slider.GetValue()
        self.created_tags_info_label.SetLabelText("Created tags waiting for saving: " + str(self.created_tags_count))
        if not self.is_list_ctrl_empty:
            self.update_tags_listing(self.file_names[self.selection])

    def load_json_file(self, file_path):
        self.current_file_path = file_path
        try:
            with open(file_path, 'r') as file:
                if not self.all_tags_data:
                    self.all_tags_data = json.load(file)
                    self.update_objects_dict_from_json()
                else:
                    self.all_tags_data.clear()
                    self.all_tags_data = json.load(file)
                    self.update_objects_dict_from_json()
        except IOError:
            wx.LogError("Cannot open the file.")
        if not self.is_list_ctrl_empty:
            self.color_file_names_after_loading_photos()

    def update_objects_dict_from_json(self):
        for list_of_objects in self.all_tags_data.items():
            for obj in list_of_objects[1]["tags"].items():
                self.objects_dict.update({str(obj[1]["object_id"]): {"label": obj[1]["label"]}})

    def color_file_names_after_loading_photos(self):
        for file_name in self.all_tags_data:
            if file_name in self.all_tags_data:
                index = 0
                for item in self.file_names:
                    if item == file_name:
                        break
                    index += 1
                self.list_ctrl.SetItemTextColour(index, wx.Colour(0, 255, 0))

    def reset_color_file_names_to_default(self):
        index = 0
        for file_name in self.file_names:
            if file_name not in self.all_tags_data:
                self.list_ctrl.SetItemTextColour(index, wx.Colour(0, 0, 0))
            index += 1

    def select_photo(self, event):
        self.selection = self.list_ctrl.GetFocusedItem()
        if self.selection >= 0:
            self.load_photo(self.row_obj_dict[self.selection])
            self.Refresh()
            self.Layout()

    def open_generator_window(self, event):
        self.second_window_closed = False
        second_window = SelectionFrame()
        pub.sendMessage("get_objects_list", object_dict=self.objects_dict)
        pub.sendMessage("get_tags_data", all_tags_data=self.all_tags_data, photos_dict=self.row_obj_dict,
                        file_names=self.file_names, folder_path=self.current_folder_path)
        second_window.Show()

    def all_objects_window(self, event):
        self.second_window_closed = False
        second_window = ObjectsListFrame()
        pub.sendMessage("update_object_list_after_open_window", object_dict=self.objects_dict)
        pub.sendMessage("get_photos_data", all_tags_data=self.all_tags_data, photos_dict=self.row_obj_dict,
                        file_names=self.file_names)
        second_window.Show()

    def update_objects_list(self, objects_list):
        self.second_window_closed = True
        self.objects_dict = objects_list
        dict_for_del = {}
        index = 0
        for tag in self.all_tags_data.items():
            for obj in tag[1]["tags"].items():
                if str(obj[1]['object_id']) not in self.objects_dict.keys():
                    dict_for_del.update({index: {"image": tag[0], "tag_id": str(obj[0])}})
                    index += 1
        for key in dict_for_del.keys():
            del (self.all_tags_data[dict_for_del[key]["image"]]["tags"][dict_for_del[key]["tag_id"]])
            if not self.all_tags_data[dict_for_del[key]["image"]]["tags"]:
                del self.all_tags_data[dict_for_del[key]["image"]]
        self.reset_color_file_names_to_default()
        if not self.is_list_ctrl_empty:
            self.update_tags_listing(self.file_names[self.selection])

    def delete_selected_tag(self, event):
        selection = self.list_ctrl_tags.GetFocusedItem()
        del (self.all_tags_data[self.file_names[self.selection]]["tags"][str(selection)])
        if not self.all_tags_data[self.file_names[self.selection]]["tags"]:
            del self.all_tags_data[self.file_names[self.selection]]
        print(self.all_tags_data)
        self.update_tags_listing(self.file_names[self.selection])
        self.reset_color_file_names_to_default()

    def show_selected_tag(self, event):
        selection = self.list_ctrl_tags.GetFocusedItem()
        if selection < 0:
            selection = 0
        file_name = self.file_names[self.selection]
        label = self.all_tags_data[file_name]['tags'][str(selection)]['label']
        bbox = self.all_tags_data[file_name]['tags'][str(selection)]['bbox']
        x, y, w, h = bbox
        window_name = "Show selected tag"
        photo = self.row_obj_dict[self.selection]
        optimized_photo = optimize_cv_image(photo)
        cv2.namedWindow(window_name)
        cv2.rectangle(optimized_photo, pt1=(x, y), pt2=(x + w, y + h), color=(0, 255, 255), thickness=2)
        cv2.putText(optimized_photo, label, (x, y + 30), fontFace=cv2.FONT_HERSHEY_PLAIN, fontScale=2,
                    color=(0, 255, 255), thickness=2)
        cv2.imshow(window_name, optimized_photo)

    def previous_image(self, event):
        if self.selection == 0:
            self.selection = len(self.row_obj_dict) - 1
        else:
            self.selection -= 1
        self.list_ctrl.Select(self.selection + 1, 0)
        self.list_ctrl.Select(self.selection, 1)
        self.load_photo(self.row_obj_dict[self.selection])
        self.Refresh()
        self.Layout()

    def next_image(self, event):
        if self.selection == (len(self.row_obj_dict) - 1):
            self.selection = 0
        else:
            self.selection += 1
        self.list_ctrl.Select(self.selection - 1, 0)
        self.list_ctrl.Select(self.selection, 1)
        self.load_photo(self.row_obj_dict[self.selection])
        self.Refresh()
        self.Layout()

    def tag_persons(self, event):
        window_name = "Make tag on the photo"
        photo = self.row_obj_dict[self.selection]
        optimized_photo = optimize_cv_image(photo)
        window_data = [window_name, optimized_photo]
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, self.draw_rectangle_with_drag, window_data)
        cv2.imshow(window_name, optimized_photo)

    def draw_rectangle_with_drag(self, event, x, y, flags, param):
        window_name = param[0]
        img = param[1]
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.second_window_closed:
                self.drawing = True
                self.ix = x
                self.iy = y

        elif event == cv2.EVENT_LBUTTONUP:
            if self.drawing:
                self.drawing = False
                cv2.rectangle(img, pt1=(self.ix, self.iy), pt2=(x, y), color=(0, 255, 255), thickness=2)
                self.iw = x - self.ix
                self.ih = y - self.iy
                cv2.imshow(window_name, img)
                if self.second_window_closed:
                    self.second_window_closed = False
                    second_window = TagDetailsFrame()
                    pub.sendMessage("get_objects_dict", objects_dict=self.objects_dict)
                    second_window.Show()

    def tag_details_listener(self, object_id, label, rate):
        if self.file_names[self.selection] in self.all_tags_data:
            self.tag_number = int(list(self.all_tags_data[self.file_names[self.selection]]["tags"].keys())[-1]) + 1
            self.tags_data = {"tags": {}}
            self.tags_data["tags"].update(self.all_tags_data[self.file_names[self.selection]]["tags"])
            print(self.tags_data)
        if self.tag_number == 0:
            self.tags_data = {
                "tags": {
                    str(self.tag_number): {
                        "object_id": object_id,
                        "label": label,
                        "rate": rate,
                        "bbox": [self.ix, self.iy, self.iw, self.ih]
                    }
                }
            }
        else:
            self.tags_data["tags"].update(
                {str(self.tag_number): {"object_id": object_id, "label": label, "rate": rate,
                                        "bbox": [self.ix, self.iy, self.iw, self.ih]}})
        self.tag_number += 1
        cv2.destroyAllWindows()
        self.created_tags_count += 1
        self.created_tags_info_label.SetLabelText("Created tags waiting for saving: " + str(self.created_tags_count))
        self.second_window_closed = True

    def close_tag_details_window(self, window_closed):
        self.second_window_closed = window_closed
        cv2.destroyAllWindows()

    def save_tags_on_the_photo(self, event):
        if self.created_tags_count > 0:
            if self.file_names[self.selection] not in self.all_tags_data:
                photo_data = {
                    self.file_names[self.selection]: {
                        "photo_rate": self.slider_value
                    }
                }
                photo_data[self.file_names[self.selection]].update(self.tags_data)
                self.all_tags_data.update(photo_data)
            else:
                self.all_tags_data[self.file_names[self.selection]].update(self.tags_data)
            self.list_ctrl.SetItemTextColour(self.selection, wx.Colour(0, 255, 0))
            self.tags_data.clear()
            self.tag_number = 0
            self.slider_value = 5
            self.created_tags_count = 0
            self.created_tags_info_label.SetLabelText(
                "Created tags waiting for saving: " + str(self.created_tags_count))
            self.Refresh()
            self.Layout()
            self.update_tags_listing(self.file_names[self.selection])
            json_string = json.dumps(self.all_tags_data, indent=2, separators=(',', ': '))
            print(json_string)

    def save_data_to_json(self):
        json_string = json.dumps(self.all_tags_data, indent=2, separators=(',', ': '))
        return json_string


class SelectionFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY, "Select objects for selection", style=wx.CAPTION, size=(700, 320))
        self.panel = wx.Panel(self)

        self.second_window_closed = True
        self.objects_dict = {}
        self.all_tags_data = {}
        self.photos_dict = {}
        self.file_names = []
        self.folder_path = ""
        self.input_data = {}
        self.input_data_index = 0

        pub.subscribe(self.get_objects_list, "get_objects_list")
        pub.subscribe(self.get_tags_data, "get_tags_data")
        pub.subscribe(self.update_input_data_list_after_add_new, "update_input_data_list_after_add_new")

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        msg_label = "List of objects for algorithm:"
        label_text = wx.StaticText(self.panel, label=msg_label)

        self.list_ctrl_objects_in_album_list = wx.ListCtrl(
            self.panel, size=(550, 150),
            style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl_objects_in_album_list.InsertColumn(0, "ID", width=50)
        self.list_ctrl_objects_in_album_list.InsertColumn(1, "Label", width=200)
        self.list_ctrl_objects_in_album_list.InsertColumn(2, "Min number of photos", width=150)
        self.list_ctrl_objects_in_album_list.InsertColumn(3, "%", width=150)
        btn_data = [("Add object to list", btn_sizer, self.add_object_to_list),
                    ("Delete object from list", btn_sizer, self.delete_object_from_list),
                    ("Run selection algorithm", btn_sizer, self.run_selection_algorithm_window),
                    ("Close window", btn_sizer, self.close_window)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)

        main_sizer.Add(label_text, 0, wx.ALL | wx.CENTER, 5)
        main_sizer.Add(self.list_ctrl_objects_in_album_list, 0, wx.ALL | wx.CENTER, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 5)

        self.panel.SetSizer(main_sizer)

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self.panel, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def update_input_data_list(self):
        self.list_ctrl_objects_in_album_list.DeleteAllItems()
        index = 0
        for obj in self.input_data.items():
            self.list_ctrl_objects_in_album_list.InsertItem(index, str(obj[1]['object_id']))
            self.list_ctrl_objects_in_album_list.SetItem(index, 1, obj[1]['object_label'])
            self.list_ctrl_objects_in_album_list.SetItem(index, 2, str(obj[1]['min_photos']))
            self.list_ctrl_objects_in_album_list.SetItem(index, 3, str(obj[1]['desire_rate']))
            index += 1
        self.list_ctrl_objects_in_album_list.Refresh()

    def get_objects_list(self, object_dict):
        self.objects_dict = object_dict

    def update_input_data_list_after_add_new(self, new_id, new_label, new_min_photos, new_desire_rate):
        self.second_window_closed = True
        if self.input_data_index == 0:
            self.input_data = {
                str(self.input_data_index): {
                    "object_id": new_id,
                    "object_label": new_label,
                    "min_photos": new_min_photos,
                    "desire_rate": new_desire_rate
                }
            }
        else:
            self.input_data.update(
                {str(self.input_data_index): {
                    "object_id": new_id,
                    "object_label": new_label,
                    "min_photos": new_min_photos,
                    "desire_rate": new_desire_rate
                }
                })
        self.input_data_index += 1
        print(self.input_data)
        self.update_input_data_list()

    def get_tags_data(self, all_tags_data, photos_dict, file_names, folder_path):
        self.all_tags_data = all_tags_data
        self.photos_dict = photos_dict
        self.file_names = file_names
        self.folder_path = folder_path

    def add_object_to_list(self, event):
        self.second_window_closed = False
        second_window = AddNewObjectToListFrame()
        pub.sendMessage("get_available_objects_dict", available_objects_dict=self.objects_dict)
        second_window.Show()

    def delete_object_from_list(self, event):
        selection = self.list_ctrl_objects_in_album_list.GetFocusedItem()
        self.input_data.pop(str(selection), None)
        print(self.input_data)
        self.update_input_data_list()

    def run_selection_algorithm_window(self, event):
        self.second_window_closed = False
        second_window = RunSelectionAlgorithmFrame()
        min_number_of_photos = 0
        max_number_of_photos = len(list(self.all_tags_data.keys()))
        for obj in self.input_data.items():
            if obj[1]['min_photos'] > min_number_of_photos:
                min_number_of_photos = obj[1]['min_photos']
        if min_number_of_photos <= max_number_of_photos:
            pub.sendMessage("get_input_data", input_data=self.input_data, all_tags_data=self.all_tags_data,
                            photos_dict=self.photos_dict, file_names=self.file_names, folder_path=self.folder_path)
            second_window.Show()
        else:
            string_for_warning = "You have a bigger sum of minimal numbers of photos for each object (" \
                                 + str(min_number_of_photos) + ") than number of photos that are tagged (" \
                                 + str(max_number_of_photos) + "). Please input data correctly"
            wx.MessageBox(string_for_warning, 'Warning', wx.OK | wx.ICON_WARNING)
            self.input_data.clear()
            self.update_input_data_list()

    def close_window(self, event):
        self.Close()


class RunSelectionAlgorithmFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY, "Run selection algorithm", style=wx.CAPTION, size=(400, 170))
        self.panel = wx.Panel(self)

        self.album_photos_limit = 0
        self.input_data = {}
        self.all_tags_data = {}
        self.photos_dict = {}
        self.file_names = []
        self.folder_path = ""
        self.min_number_of_photos = 0
        self.max_number_of_photos = 0
        self.album = []

        pub.subscribe(self.get_input_data, "get_input_data")

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        msg_label = "How many photos should be in album?"
        self.label_text = wx.StaticText(self.panel, label=msg_label)

        album_photos_limit_ctrl = wx.lib.masked.numctrl.NumCtrl(self.panel)
        album_photos_limit_ctrl.Bind(wx.EVT_TEXT, self.text_typed)
        album_photos_limit_ctrl.SetAllowNegative(False)

        btn_data = [("Run algorithm", btn_sizer, self.run_algorithm_button),
                    ("Cancel", btn_sizer, self.cancel_button)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)

        main_sizer.Add(self.label_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(album_photos_limit_ctrl, 0, wx.CENTER, border=15)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 5)

        self.panel.SetSizer(main_sizer)

    def text_typed(self, event):
        self.album_photos_limit = int(event.GetString())

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self.panel, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def get_input_data(self, input_data, all_tags_data, photos_dict, file_names, folder_path):
        self.input_data = input_data
        self.all_tags_data = all_tags_data
        self.photos_dict = photos_dict
        self.file_names = file_names
        self.folder_path = folder_path
        self.max_number_of_photos = len(list(self.all_tags_data.keys()))
        for obj in self.input_data.items():
            if obj[1]['min_photos'] > self.min_number_of_photos:
                self.min_number_of_photos = obj[1]['min_photos']
        string_for_label = "How many photos should be in album? (" + str(self.min_number_of_photos) + " - " + str(
            self.max_number_of_photos) + " photos)"
        self.label_text.SetLabelText(string_for_label)

    def run_algorithm_button(self, event):
        if self.min_number_of_photos <= self.album_photos_limit <= self.max_number_of_photos:
            self.selection_algorithm()
            self.Close()
        else:
            wx.MessageBox('Album photos limit is not correct!', 'Warning',
                          wx.OK | wx.ICON_WARNING)

    def selection_algorithm(self):
        photos = {}
        objects_to_album = {}
        C = 0.01
        C_for_others = 0.01
        for data in self.input_data.items():
            objects_to_album[data[1]['object_id']] = {'min_photos': data[1]['min_photos'],
                                                      'actual_photos': 0,
                                                      'desire_rate': (data[1]['desire_rate'] / 100),
                                                      'desire_rate_dec': ((data[1]['desire_rate'] / 100) / data[1][
                                                          'min_photos'])}
        for image in self.all_tags_data.keys():
            photos[image] = {}
            photos[image]['global_rate'] = self.all_tags_data[image]['photo_rate']
            list_of_objects = []
            cnt = 1
            for obj in self.all_tags_data[image]['tags'].items():
                list_of_objects.append(obj[1]['object_id'])
                if obj[1]['object_id'] in objects_to_album.keys():
                    cnt += 1
                    photos[image]['global_rate'] += obj[1]['rate']
            photos[image]['global_rate'] = photos[image]['global_rate'] / cnt
            photos[image]['final_rate'] = 0
            photos[image]['objects'] = list_of_objects

        for i in range(self.album_photos_limit):
            min_fulfilled = True
            for obj in objects_to_album.items():
                if obj[1]['actual_photos'] < obj[1]['min_photos']:
                    min_fulfilled = False

            for image in photos.items():
                cnt = 0
                desire_rate = 0
                image[1]['final_rate'] = image[1]['global_rate']
                for obj in image[1]['objects']:
                    if obj in objects_to_album.keys():
                        desire_rate += objects_to_album[obj]['desire_rate']
                        cnt += 1
                if cnt > 0:
                    desire_rate = desire_rate / cnt
                else:
                    desire_rate = C_for_others
                image[1]['final_rate'] *= desire_rate
            best_final_rate = 0
            best_photo = ""
            for image in photos.items():
                if image[1]['final_rate'] > best_final_rate:
                    best_photo = image[0]
                    best_final_rate = image[1]['final_rate']
            for obj in photos[best_photo]['objects']:
                if obj in objects_to_album.keys():
                    if objects_to_album[obj]['actual_photos'] < objects_to_album[obj]['min_photos']:
                        objects_to_album[obj]['desire_rate'] -= (objects_to_album[obj]['desire_rate_dec'] * C)
                        objects_to_album[obj]['actual_photos'] += 1
            photos.pop(best_photo, None)
            self.album.append([best_photo, best_final_rate])
        self.generate_album()

    def generate_album(self):
        path_for_album = "./album"
        if os.path.exists(path_for_album) and os.path.isdir(path_for_album):
            shutil.rmtree(path_for_album)
        os.mkdir(path_for_album)
        for photo in self.album:
            path_to_file = self.folder_path + "\\" + photo[0]
            shutil.copy(path_to_file, path_for_album)
        with open(path_for_album + "/selection_result.txt", "w") as data_file:
            for item in self.album:
                data_file.write("%s\n" % item)

    def cancel_button(self, event):
        self.Close()


class AddNewObjectToListFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY, "Add new object", style=wx.CAPTION, size=(600, 350))
        self.panel = wx.Panel(self)

        self.id = 0
        self.label = ""
        self.min_photos = 0
        self.desire_rate = 0
        self.objects_dict = {}

        pub.subscribe(self.get_available_objects_dict, "get_available_objects_dict")

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        obj_on_tag_label = "Object on tag:"
        obj_on_tag_text = wx.StaticText(self.panel, label=obj_on_tag_label)

        self.available_objects_choice = wx.Choice(self.panel, 0, choices=[], size=(300, 50))

        min_photos_label = "Minimum number of photos with this object:"
        min_photos_text = wx.StaticText(self.panel, label=min_photos_label)

        min_photos_ctrl = wx.lib.masked.numctrl.NumCtrl(self.panel)
        min_photos_ctrl.Bind(wx.EVT_TEXT, self.text_typed)
        min_photos_ctrl.SetAllowNegative(False)

        desire_rate = "Desire rate:"
        desire_text = wx.StaticText(self.panel, label=desire_rate)

        self.input_data_slider = wx.Slider(self.panel, value=self.desire_rate, minValue=0, maxValue=100, size=(400, 50),
                                           style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.input_data_slider.Bind(wx.EVT_SLIDER, self.on_slider_scroll)

        btn_data = [("Add object to list", btn_sizer, self.add_button),
                    ("Cancel", btn_sizer, self.cancel_button)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)

        main_sizer.Add(obj_on_tag_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(self.available_objects_choice, 0, wx.CENTER, border=15)
        main_sizer.Add(min_photos_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(min_photos_ctrl, 0, wx.CENTER, border=15)
        main_sizer.Add(desire_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(self.input_data_slider, 0, wx.CENTER | wx.TOP, border=20)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 5)

        self.panel.SetSizer(main_sizer)

    def text_typed(self, event):
        self.min_photos = int(event.GetString())

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self.panel, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def on_slider_scroll(self, event):
        obj = event.GetEventObject()
        self.desire_rate = obj.GetValue()
        font = self.GetFont()
        font.SetPointSize(self.input_data_slider.GetValue())

    def get_available_objects_dict(self, available_objects_dict):
        self.objects_dict = available_objects_dict
        for obj in self.objects_dict.items():
            string = obj[0] + ". " + obj[1]['label']
            self.available_objects_choice.Append(string)
        self.available_objects_choice.SetSelection(0)

    def add_button(self, event):
        selection = self.available_objects_choice.GetSelection()
        selected_object = self.available_objects_choice.GetItems()[selection]
        object_id = selected_object.split(".")[0]
        self.label = self.objects_dict[object_id]['label']
        pub.sendMessage("update_input_data_list_after_add_new", new_id=int(object_id), new_label=self.label,
                        new_min_photos=self.min_photos, new_desire_rate=self.desire_rate)
        self.label = ""
        self.id = 0
        self.Close()

    def cancel_button(self, event):
        self.Close()


class TagDetailsFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY, "Tag Details", size=(600, 320))
        self.panel = wx.Panel(self)
        self.value = 5
        self.label = ""
        self.objects_list = {}
        self.second_window_closed = True

        pub.subscribe(self.get_objects_dict, "get_objects_dict")

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        msg_label = "Object on tag:"
        label_text = wx.StaticText(self.panel, label=msg_label)

        self.object_list_choice = wx.Choice(self.panel, 0, choices=[], size=(300, 50))

        msg_rate = "Tag\'s rate:"
        rate_text = wx.StaticText(self.panel, label=msg_rate)

        self.slider = wx.Slider(self.panel, value=self.value, minValue=0, maxValue=10, size=(350, 50),
                                style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.slider.Bind(wx.EVT_SLIDER, self.on_slider_scroll)

        btn_data = [("Save tag and close", btn_sizer, self.on_save_and_close),
                    ("Close", btn_sizer, self.close_window)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)

        main_sizer.Add(label_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(self.object_list_choice, 0, wx.CENTER, border=15)
        main_sizer.Add(rate_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(self.slider, 0, wx.CENTER | wx.TOP, border=20)
        main_sizer.Add(btn_sizer, 0, wx.CENTER | wx.BOTTOM, border=10)

        self.panel.SetSizer(main_sizer)

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self.panel, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def get_objects_dict(self, objects_dict):
        self.objects_list = objects_dict
        for obj in self.objects_list.items():
            string = obj[0] + ". " + obj[1]['label']
            self.object_list_choice.Append(string)
        self.object_list_choice.SetSelection(0)

    def on_slider_scroll(self, event):
        obj = event.GetEventObject()
        self.value = obj.GetValue()
        font = self.GetFont()
        font.SetPointSize(self.slider.GetValue())

    def on_save_and_close(self, event):
        selection = self.object_list_choice.GetSelection()
        selected_object = self.object_list_choice.GetItems()[selection]
        object_id = selected_object.split(".")[0]
        self.label = self.objects_list[object_id]['label']
        pub.sendMessage("tag_details_listener", object_id=int(object_id), label=self.label, rate=self.value)
        self.label = ""
        self.value = 5
        self.Close()

    def close_window(self, event):
        pub.sendMessage("close_tag_details_window", window_closed=True)
        self.Close()


class ObjectsListFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY, "All objects list", style=wx.CAPTION, size=(600, 320))
        self.panel = wx.Panel(self)

        self.second_window_closed = True
        self.objects_list = {}
        self.all_tags_data = {}
        self.photos_dict = {}
        self.file_names = []

        pub.subscribe(self.update_object_list_after_open_window, "update_object_list_after_open_window")
        pub.subscribe(self.update_object_list_after_add_new, "update_object_list_after_add_new")
        pub.subscribe(self.get_photos_data, "get_photos_data")

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        msg_label = "List of all objects:"
        label_text = wx.StaticText(self.panel, label=msg_label)

        self.list_ctrl_objects_list = wx.ListCtrl(
            self.panel, size=(450, 150),
            style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl_objects_list.InsertColumn(0, "ID", width=50)
        self.list_ctrl_objects_list.InsertColumn(1, "Label", width=380)
        btn_data = [("Add new object", btn_sizer, self.add_new_object),
                    ("Delete selected object", btn_sizer, self.delete_selected_object),
                    ("Show object\'s photos", btn_sizer, self.show_object_photos),
                    ("Close window", btn_sizer, self.close_window)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)

        main_sizer.Add(label_text, 0, wx.ALL | wx.CENTER, 5)
        main_sizer.Add(self.list_ctrl_objects_list, 0, wx.ALL | wx.CENTER, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 5)

        self.panel.SetSizer(main_sizer)

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self.panel, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def update_object_list(self):
        self.list_ctrl_objects_list.DeleteAllItems()
        index = 0
        for obj in self.objects_list.items():
            self.list_ctrl_objects_list.InsertItem(index, obj[0])
            self.list_ctrl_objects_list.SetItem(index, 1, obj[1]['label'])
            index += 1
        self.list_ctrl_objects_list.Refresh()

    def update_object_list_after_open_window(self, object_dict):
        self.objects_list = object_dict
        self.update_object_list()

    def update_object_list_after_add_new(self, new_id, new_label):
        self.second_window_closed = True
        self.objects_list.update({str(new_id): {"label": new_label}})
        self.update_object_list()

    def get_photos_data(self, all_tags_data, photos_dict, file_names):
        self.all_tags_data = all_tags_data
        self.photos_dict = photos_dict
        self.file_names = file_names

    def add_new_object(self, event):
        self.second_window_closed = False
        second_window = AddNewObjectFrame()
        if self.objects_list:
            last_id = int(list(self.objects_list.keys())[-1])
        else:
            last_id = -1
        pub.sendMessage("get_last_id", last_id=last_id)
        second_window.Show()

    def delete_selected_object(self, event):
        selection = self.list_ctrl_objects_list.GetFocusedItem()
        self.objects_list.pop(str(selection), None)
        print(self.objects_list)
        self.update_object_list()

    def show_object_photos(self, event):
        self.second_window_closed = False
        selection = self.list_ctrl_objects_list.GetFocusedItem()
        if selection < 0:
            selection = 0
        obj_id = int(list(self.objects_list.keys())[selection])
        obj_label = self.objects_list[list(self.objects_list.keys())[selection]]['label']
        second_window = ShowObjectPhotosFrame()
        pub.sendMessage("get_data_about_selection", obj_id=obj_id, obj_label=obj_label)
        pub.sendMessage("get_data_about_photos", all_tags_data=self.all_tags_data, photos_dict=self.photos_dict,
                        file_names=self.file_names)
        second_window.Show()

    def close_window(self, event):
        pub.sendMessage("update_objects_list", objects_list=self.objects_list)
        self.Close()


class AddNewObjectFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY, "Add new object", style=wx.CAPTION, size=(400, 170))
        self.panel = wx.Panel(self)

        self.label = ""
        self.id = 0

        pub.subscribe(self.get_last_id, "get_last_id")

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        msg_label = "Tag\'s label:"
        label_text = wx.StaticText(self.panel, label=msg_label)

        label_ctrl = wx.TextCtrl(self.panel)
        label_ctrl.Bind(wx.EVT_TEXT, self.text_typed)

        btn_data = [("Add new object", btn_sizer, self.add_button),
                    ("Cancel", btn_sizer, self.cancel_button)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)

        main_sizer.Add(label_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(label_ctrl, 0, wx.CENTER, border=15)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 5)

        self.panel.SetSizer(main_sizer)

    def text_typed(self, event):
        self.label = event.GetString()

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self.panel, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def add_button(self, event):
        pub.sendMessage("update_object_list_after_add_new", new_id=self.id, new_label=self.label)
        self.label = ""
        self.id = 0
        self.Close()

    def cancel_button(self, event):
        self.Close()

    def get_last_id(self, last_id):
        self.id = last_id + 1


class ShowObjectPhotosFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, wx.ID_ANY, "Show selected object photos", style=wx.CAPTION, size=(600, 320))
        self.panel = wx.Panel(self)

        self.all_tags_data = {}
        self.photos_dict = {}
        self.file_names = []
        self.bbox_data = {}
        self.obj_id = 0
        self.obj_label = ""
        self.is_data_loaded = False

        pub.subscribe(self.get_data_about_selection, "get_data_about_selection")
        pub.subscribe(self.get_data_about_photos, "get_data_about_photos")

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        msg_label = "All photos where is object "
        self.label_text = wx.StaticText(self.panel, label=msg_label)

        self.list_ctrl_photos_list = wx.ListCtrl(
            self.panel, size=(450, 150),
            style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl_photos_list.InsertColumn(0, "File name", width=300)
        self.list_ctrl_photos_list.InsertColumn(1, "Tag\'s rate on photo", width=150)
        btn_data = [("Show photo", btn_sizer, self.show_photo),
                    ("Close window", btn_sizer, self.close_window)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)

        main_sizer.Add(self.label_text, 0, wx.ALL | wx.CENTER, 5)
        main_sizer.Add(self.list_ctrl_photos_list, 0, wx.ALL | wx.CENTER, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.CENTER, 5)

        self.panel.SetSizer(main_sizer)

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self.panel, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def get_data_about_selection(self, obj_id, obj_label):
        self.obj_id = obj_id
        self.obj_label = obj_label
        self.label_text.SetLabelText("All photos where is object: " + str(self.obj_id) + ". " + self.obj_label)

    def get_data_about_photos(self, all_tags_data, photos_dict, file_names):
        self.all_tags_data = all_tags_data
        self.photos_dict = photos_dict
        self.file_names = file_names
        if file_names:
            self.is_data_loaded = True
        self.update_list_ctrl_data()

    def update_list_ctrl_data(self):
        self.list_ctrl_photos_list.DeleteAllItems()
        index = 0
        for tag in self.all_tags_data.items():
            for obj in tag[1]["tags"].items():
                if obj[1]['object_id'] == self.obj_id:
                    self.list_ctrl_photos_list.InsertItem(index, tag[0])
                    self.list_ctrl_photos_list.SetItem(index, 1, str(obj[1]['rate']))
                    self.bbox_data.update({tag[0]: {'bbox': obj[1]['bbox']}})
                    index += 1
        self.list_ctrl_photos_list.Refresh()

    def show_photo(self, event):
        if self.is_data_loaded:
            selection = self.list_ctrl_photos_list.GetFocusedItem()
            selected_file_name = self.list_ctrl_photos_list.GetItemText(selection, 0)
            index = self.file_names.index(selected_file_name)
            bbox = self.bbox_data[selected_file_name]['bbox']
            x, y, w, h = bbox
            window_name = "Show selected photo"
            photo = self.photos_dict[index]
            optimized_photo = optimize_cv_image(photo)
            cv2.namedWindow(window_name)
            cv2.rectangle(optimized_photo, pt1=(x, y), pt2=(x + w, y + h), color=(0, 255, 255), thickness=2)
            cv2.putText(optimized_photo, self.obj_label, (x, y + 30), fontFace=cv2.FONT_HERSHEY_PLAIN, fontScale=2,
                        color=(0, 255, 255), thickness=2)
            cv2.imshow(window_name, optimized_photo)
        else:
            wx.MessageBox('Images are not loaded. Select folder with images.', 'Warning',
                          wx.OK | wx.ICON_WARNING)

    def close_window(self, event):
        self.Close()


class AppFrame(wx.Frame):
    def __init__(self):
        super(AppFrame, self).__init__(parent=None, title="Album Generator")
        self.panel = AppPanel(self)
        self.create_menu()
        screensize = wx.DisplaySize()
        w = screensize[0] * 0.75
        h = screensize[1] * 0.85
        self.SetMinSize((w, h))
        self.Maximize()
        self.Show()

    def create_menu(self):
        menu_bar = wx.MenuBar()
        file_menu = wx.Menu()
        open_folder_menu_item = file_menu.Append(
            wx.ID_ANY, 'Open folder', 'Open a folder with photos'
        )
        menu_bar.Append(file_menu, '&File')
        self.Bind(
            event=wx.EVT_MENU,
            handler=self.on_open_folder,
            source=open_folder_menu_item,
        )
        json_menu = wx.Menu()
        save_json_menu_item = json_menu.Append(
            wx.ID_ANY, 'Save data to JSON', 'Save data with all tags to JSON file',
        )
        load_data_from_json_menu_item = json_menu.Append(
            wx.ID_ANY, 'Load data from JSON', 'Load data with all tags from JSON file'
        )
        menu_bar.Append(json_menu, '&JSON')
        self.Bind(
            event=wx.EVT_MENU,
            handler=self.on_save_json,
            source=save_json_menu_item
        )
        self.Bind(
            event=wx.EVT_MENU,
            handler=self.on_load_from_json,
            source=load_data_from_json_menu_item
        )
        self.SetMenuBar(menu_bar)

    def on_open_folder(self, event):
        title = "Choose a directory:"
        dlg = wx.DirDialog(self, title, style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            self.panel.update_files_listing(dlg.GetPath())
        dlg.Destroy()

    def on_save_json(self, event):
        json_string = self.panel.save_data_to_json()
        file_name = datetime.now().strftime("%Y-%m-%d_%I-%M-%S_%p")
        with open(file_name + ".json", "w") as data_file:
            data_file.write(json_string + '\n')

    def on_load_from_json(self, event):
        title = "Choose a JSON file:"
        dlg = wx.FileDialog(self, title, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
                            wildcard="JSON files (*.json)|*.json")
        if dlg.ShowModal() == wx.ID_OK:
            self.panel.load_json_file(dlg.GetPath())
            dlg.Destroy()


if __name__ == '__main__':
    app = wx.App(False)
    frame = AppFrame()
    app.MainLoop()
