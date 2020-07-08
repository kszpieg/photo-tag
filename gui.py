import cv2
import wx
import glob
import os
import time
from pathlib import Path
from crop_objects import crop_objects
from image_converter import wxBitmapFromCvImage


def optimalize_bitmap_person_height(bitmap):
    if bitmap.GetHeight() > 300:
        image = bitmap.ConvertToImage()
        calculated_width = (bitmap.GetWidth() * 300) / bitmap.GetHeight()
        bitmap = wx.Bitmap(image.Scale(calculated_width, 300))
    return bitmap


def optimalize_bitmap_person_width(bitmap):
    if bitmap.GetWidth() > 700:
        image = bitmap.ConvertToImage()
        calculated_height = (bitmap.GetHeight() * 700) / bitmap.GetWidth()
        bitmap = wx.Bitmap(image.Scale(700, calculated_height))
    return bitmap


class AppPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        btn_main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_recognized_sizer = wx.BoxSizer(wx.HORIZONTAL)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.row_obj_dict = {}
        self.list_of_images = []
        self.current_person = 0
        self.total_persons = 0

        self.list_ctrl = wx.ListCtrl(
            self, size=(650, 150),
            style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl.InsertColumn(0, "File name", width=280)
        self.list_ctrl.InsertColumn(1, "File extension", width=100)
        left_sizer.Add(self.list_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        btn_data = [("Run recognizer", btn_main_sizer, self.on_run),
                    ("Run recognizer for all", btn_main_sizer, self.on_run_all)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)
        left_sizer.Add(btn_main_sizer, 0, wx.CENTER)
        bmp_person = wx.Image(200, 300)
        self.image_ctrl1 = wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(bmp_person))
        left_sizer.Add(self.image_ctrl1, 0, wx.ALL | wx.CENTER, 5)
        self.image_label = wx.StaticText(self, label="")
        left_sizer.Add(self.image_label, 0, wx.ALL | wx.CENTER, 5)
        btn_data = [("Previous", btn_recognized_sizer, self.on_previous),
                    ("Choose person", btn_recognized_sizer, self.on_save_person),
                    ("Next", btn_recognized_sizer, self.on_next)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)
        left_sizer.Add(btn_recognized_sizer, 0, wx.CENTER)

        bmp_image = wx.Image(400, 400)
        self.image_ctrl2 = wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(bmp_image))
        right_sizer.Add(self.image_ctrl2, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        main_sizer.Add(left_sizer, wx.ALIGN_LEFT, 5)
        main_sizer.Add(right_sizer, wx.ALIGN_RIGHT, 5)
        self.SetSizer(main_sizer)

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def on_run(self, event):
        selection = self.list_ctrl.GetFocusedItem()
        if selection >= 0:
            photo = self.row_obj_dict[selection]
            result_image, detected_objects = recognize_persons(photo)
            self.list_of_images = crop_objects(photo, detected_objects)
            converted_image = wxBitmapFromCvImage(result_image)
            bitmap = optimalize_bitmap_person_width(wx.Bitmap(converted_image))
            self.image_ctrl2.SetBitmap(bitmap)
            self.update_detected_persons()

    def on_run_all(self):
        print("Not implemented")

    def on_previous(self, event):
        if self.current_person == 0:
            self.current_person = self.total_persons - 1
        else:
            self.current_person -= 1
        converted_image = wxBitmapFromCvImage(self.list_of_images[self.current_person])
        bitmap = optimalize_bitmap_person_height(wx.Bitmap(converted_image))
        self.image_ctrl1.SetBitmap(bitmap)
        self.image_label.SetLabelText("Person " + str(self.current_person))

    def on_next(self, event):
        if self.current_person == self.total_persons - 1:
            self.current_person = 0
        else:
            self.current_person += 1
        converted_image = wxBitmapFromCvImage(self.list_of_images[self.current_person])
        bitmap = optimalize_bitmap_person_height(wx.Bitmap(converted_image))
        self.image_ctrl1.SetBitmap(bitmap)
        self.image_label.SetLabelText("Person " + str(self.current_person))

    def on_save_person(self):
        print("Not implemented")

    def update_detected_persons(self):
        self.current_person = 0
        self.total_persons = len(self.list_of_images)
        converted_image = wxBitmapFromCvImage(self.list_of_images[self.current_person])
        bitmap = optimalize_bitmap_person_height(wx.Bitmap(converted_image))
        self.image_ctrl1.SetBitmap(bitmap)
        self.image_label.SetLabelText("Person " + str(self.current_person))

    def update_files_listing(self, folder_path):
        self.current_folder_path = folder_path
        self.list_ctrl.ClearAll()

        self.list_ctrl.InsertColumn(0, "File name", width=250)
        self.list_ctrl.InsertColumn(1, "Date", width=150)
        self.list_ctrl.InsertColumn(2, "File extension", width=100)
        self.list_ctrl.InsertColumn(3, "Size", width=100)

        photos = glob.glob(folder_path + "/*.jpg")
        photo_objects = []
        index = 0
        for photo in photos:
            photo_object = cv2.imread(photo)
            self.list_ctrl.InsertItem(index, Path(photo).stem)
            self.list_ctrl.SetItem(index, 1, str(time.strftime('%d/%m/%Y', time.gmtime(os.path.getmtime(photo)))))
            self.list_ctrl.SetItem(index, 2, Path(photo).suffix)
            self.list_ctrl.SetItem(index, 3, str(os.path.getsize(photo)) + " B")
            photo_objects.append(photo_object)
            self.row_obj_dict[index] = photo_object
            index += 1


class AppFrame(wx.Frame):
    def __init__(self):
        super(AppFrame, self).__init__(parent=None, title="Person Recognizer")
        self.panel = AppPanel(self)
        self.create_menu()
        self.SetMinSize((1450, 650))
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
        self.SetMenuBar(menu_bar)

    def on_open_folder(self, event):
        title = "Choose a directory:"
        dlg = wx.DirDialog(self, title, style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            self.panel.update_files_listing(dlg.GetPath())
        dlg.Destroy()


if __name__ == '__main__':
    app = wx.App(False)
    frame = AppFrame()
    app.MainLoop()
