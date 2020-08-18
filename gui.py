from datetime import datetime

import cv2
import numpy as np
import wx
import glob
import os
import time
import json
from pathlib import Path
from crop_objects import crop_objects
from image_converter import wxBitmapFromCvImage
from pubsub import pub


def optimize_bitmap_person(bitmap):
    if bitmap.GetWidth() > 700:
        image = bitmap.ConvertToImage()
        calculated_height = (bitmap.GetHeight() * 700) / bitmap.GetWidth()
        bitmap = wx.Bitmap(image.Scale(700, calculated_height))
    if bitmap.GetHeight() > 700:
        image = bitmap.ConvertToImage()
        calculated_width = (bitmap.GetWidth() * 700) / bitmap.GetHeight()
        bitmap = wx.Bitmap(image.Scale(calculated_width, 700))
    return bitmap


def optimize_cv_image(image):
    h, w = image.shape[:2]
    if w > 700:
        calculated_height = int((h * 700) / w)
        resized_img = cv2.resize(image, (700, calculated_height))
        image = resized_img
    if h > 700:
        calculated_width = int((w * 700) / h)
        resized_img = cv2.resize(image, (calculated_width, 700))
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
        self.created_tags_info_label.SetLabelText("Created tags waiting for saving: " + str(self.created_tags_count))
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

    def select_photo(self, event):
        self.selection = self.list_ctrl.GetFocusedItem()
        if self.selection >= 0:
            self.load_photo(self.row_obj_dict[self.selection])
            self.Refresh()
            self.Layout()

    def open_generator_window(self):
        print("Not implemented")

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
        if self.tag_number == 0:
            self.tags_data = {
                "tags": {
                    self.tag_number: {
                        "object_id": object_id,
                        "label": label,
                        "rate": rate,
                        "bbox": [self.ix, self.iy, self.iw, self.ih]
                    }
                }
            }
        else:
            self.tags_data["tags"].update(
                {self.tag_number: {"object_id": object_id, "label": label, "rate": rate,
                                   "bbox": [self.ix, self.iy, self.iw, self.ih]}})
        self.tag_number += 1
        json_string = json.dumps(self.tags_data)
        cv2.destroyAllWindows()
        self.created_tags_count += 1
        self.created_tags_info_label.SetLabelText("Created tags waiting for saving: " + str(self.created_tags_count))
        self.second_window_closed = True

    def close_tag_details_window(self, window_closed):
        self.second_window_closed = window_closed
        cv2.destroyAllWindows()

    def save_tags_on_the_photo(self, event):
        photo_data = {
            self.file_names[self.selection]: {
                "photo_rate": self.slider_value
            }
        }
        photo_data[self.file_names[self.selection]].update(self.tags_data)
        self.all_tags_data.update(photo_data)
        self.list_ctrl.SetItemTextColour(self.selection, wx.Colour(0, 255, 0))
        self.tags_data.clear()
        self.tag_number = 0
        self.slider_value = 5
        self.created_tags_count = 0
        self.created_tags_info_label.SetLabelText("Created tags waiting for saving: " + str(self.created_tags_count))
        self.Refresh()
        self.Layout()
        json_string = json.dumps(self.all_tags_data, indent=2, separators=(',', ': '))
        print(json_string)

    def save_data_to_json(self):
        json_string = json.dumps(self.all_tags_data, indent=2, separators=(',', ': '))
        return json_string


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

        # checkbox_eyes = wx.CheckBox(self.panel, label="Person's eyes are closed")
        # checkbox_blurred = wx.CheckBox(self.panel, label="Person is blurred")
        # checkbox_others = wx.CheckBox(self.panel, label="Others defects (red eyes, look not at the camera, etc.)")

        btn_data = [("Save tag and close", btn_sizer, self.on_save_and_close),
                    ("Close", btn_sizer, self.close_window)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)

        main_sizer.Add(label_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(self.object_list_choice, 0, wx.CENTER, border=15)
        main_sizer.Add(rate_text, 0, wx.TOP | wx.CENTER, border=15)
        main_sizer.Add(self.slider, 0, wx.CENTER | wx.TOP, border=20)
        # main_sizer.Add(checkbox_eyes, 0, wx.EXPAND | wx.CENTER, border=15)
        # main_sizer.Add(checkbox_blurred, 0, wx.EXPAND | wx.CENTER, border=15)
        # main_sizer.Add(checkbox_others, 0, wx.EXPAND | wx.CENTER, border=15)
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
        pub.sendMessage("tag_details_listener", object_id=object_id, label=self.label, rate=self.value)
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
        self.SetMinSize((1450, 750))
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
        elif dlg.ShowModal() == wx.ID_CANCEL:
            return


if __name__ == '__main__':
    app = wx.App(False)
    frame = AppFrame()
    app.MainLoop()
