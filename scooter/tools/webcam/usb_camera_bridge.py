import cv2
import time

print("[usb_cam] Starting USB camera bridge...")
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

while True:
    ret, frame = cap.read()
    if ret:
        cv2.imwrite("/tmp/camera_frame.jpg", frame)
    else:
        print("[usb_cam] Failed to read frame")
    time.sleep(0.2)
