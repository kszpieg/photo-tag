import cv2
import wx
import glob
import os
import time
from pathlib import Path
from crop_objects import crop_objects
from image_converter import wxBitmapFromCvImage


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
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.row_obj_dict = {}
        self.file_names = []
        self.selection = 0
        self.label_photo = ""

        self.list_ctrl = wx.ListCtrl(
            self, size=(650, 150),
            style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl.InsertColumn(0, "File name", width=280)
        self.list_ctrl.InsertColumn(1, "File extension", width=100)
        left_sizer.Add(self.list_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        btn_data = [("Select image", btn_main_sizer, self.select_photo),
                    ("Generate album", btn_main_sizer, self.open_generator_window)]
        for data in btn_data:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)
        left_sizer.Add(btn_main_sizer, 0, wx.CENTER)

        bmp_image = wx.Image(wx.EXPAND, wx.EXPAND)
        self.image_ctrl = wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(bmp_image))
        right_sizer.Add(self.image_ctrl, 0, wx.ALL | wx.ALIGN_LEFT, 5)

        self.image_label = wx.StaticText(self, label="")
        right_sizer.Add(self.image_label, 0, wx.ALL | wx.CENTER, 5)

        btn_data_under_photo = [("Previous image", btn_image_sizer, self.previous_image),
                    ("Make tag", btn_image_sizer, self.tag_persons),
                    ("Save tags", btn_image_sizer, self.save_tags_on_the_photo),
                    ("Next image", btn_image_sizer, self.next_image)]
        for data in btn_data_under_photo:
            label, sizer, handler = data
            self.btn_builder(label, sizer, handler)
        right_sizer.Add(btn_image_sizer, 0, wx.CENTER)

        main_sizer.Add(left_sizer, wx.ALIGN_LEFT, 5)
        main_sizer.Add(right_sizer, wx.ALIGN_RIGHT, 5)
        self.SetSizer(main_sizer)

    def btn_builder(self, label, sizer, handler):
        btn = wx.Button(self, label=label)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

    def select_photo(self, event):
        self.selection = self.list_ctrl.GetFocusedItem()
        if self.selection >= 0:
            photo = self.row_obj_dict[self.selection]
            #result_image, detected_objects = recognize_persons(photo)
            #self.list_of_images = crop_objects(photo, detected_objects)
            converted_image = wxBitmapFromCvImage(photo)
            bitmap = optimize_bitmap_person(wx.Bitmap(converted_image))
            self.image_ctrl.SetBitmap(bitmap)
            self.image_label.SetLabelText(self.file_names[self.selection])
            self.Refresh()
            self.Layout()

    def previous_image(self, event):
        if self.selection == 0:
            self.selection = len(self.row_obj_dict) - 1
        else:
            self.selection -= 1
        photo = self.row_obj_dict[self.selection]
        converted_image = wxBitmapFromCvImage(photo)
        bitmap = optimize_bitmap_person(wx.Bitmap(converted_image))
        self.image_ctrl.SetBitmap(bitmap)
        self.image_label.SetLabelText(self.file_names[self.selection])

    def next_image(self, event):
        if self.selection == (len(self.row_obj_dict) - 1):
            self.selection = 0
        else:
            self.selection += 1
        photo = self.row_obj_dict[self.selection]
        converted_image = wxBitmapFromCvImage(photo)
        bitmap = optimize_bitmap_person(wx.Bitmap(converted_image))
        self.image_ctrl.SetBitmap(bitmap)
        self.image_label.SetLabelText(self.file_names[self.selection])

    def tag_persons(self, event):
        window_name = "Make tag on the photo"
        photo = self.row_obj_dict[self.selection]
        optimized_photo = optimize_cv_image(photo)
        cv2.namedWindow(window_name)
        cv2.imshow(window_name, optimized_photo)

    def save_tags_on_the_photo(self, event):
        print("Not implemented")

    def open_generator_window(self):
        print("Not implemented")


    def update_files_listing(self, folder_path):
        self.current_folder_path = folder_path
        self.list_ctrl.ClearAll()
        self.file_names.clear()

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
            self.file_names.append(Path(photo).stem + Path(photo).suffix)
            self.list_ctrl.SetItem(index, 1, str(time.strftime('%d/%m/%Y', time.gmtime(os.path.getmtime(photo)))))
            self.list_ctrl.SetItem(index, 2, Path(photo).suffix)
            self.list_ctrl.SetItem(index, 3, str(os.path.getsize(photo)) + " B")
            photo_objects.append(photo_object)
            self.row_obj_dict[index] = photo_object
            index += 1


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
