import cv2
import numpy as np


def crop_objects(image, objects):
    img = np.copy(image)
    img = cv2.resize(img, None, fx=0.7, fy=0.7)
    boxes = objects
    list_of_images = []

    for i in range(len(boxes)):
        x, y, w, h = boxes[i]
        new_img = img[y:y + h, x:x + w]
        list_of_images.append(new_img)

    return list_of_images
