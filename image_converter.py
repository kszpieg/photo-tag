import cv2
import wx


def wxBitmapFromCvImage(image):
    if len(image.shape) < 3:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    else:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w = image.shape[:2]
    wxImage = wx.Image(w, h, image)
    bitmap = wx.Bitmap(wxImage)

    return bitmap
