# -*- coding: utf-8 -*-
"""Kalman_filter_tracking.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1vbRwTpKt7nPQdCn0PYsPFM71Fp-GIi2t
"""
# Stationary coordinates detected: (10sec.mp4)
# [((1894.7992769129137, 303.175568075741), 34), ((2333.0154160860784, 1482.0646242436044), 500)]
# [((1894.7992769129137, 303.175568075741), 34), ((2333.0154160860784, 1482.0646242436044), 500), ((1008.7924158432904, 313.01178965849033), 17)]


import pandas as pd
from numpy.linalg import inv
import numpy as np
import math
import cv2
import torch
from matplotlib import pyplot as plt
import pickle as pkl
import os

import torch
from ultralytics import YOLO

print("Current working directory:", os.getcwd())
model = YOLO('models/shuttle_detection/weights/best.pt')


# Ensure to use the GPU if available
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)

def draw_prediction(img: np.ndarray,
                    class_name: str,
                    df: pd.core.series.Series,
                    color: tuple = (255, 0, 0)):
    '''
    Function to draw prediction around the bounding box identified by the YOLO
    The Function also displays the confidence score top of the bounding box
    '''

    cv2.rectangle(img, (int(df.xmin), int(df.ymin)),
                  (int(df.xmax), int(df.ymax)), color, 2)
    cv2.putText(img, class_name + " " + str(round(df.confidence, 2)),
                (int(df.xmin) - 10, int(df.ymin) - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return img

class KalmanFilter():
    def __init__(self,
                 xinit: int = 0,
                 yinit: int = 0,
                 fps: int = 30,
                 std_a: float = 0.001,
                 std_x: float = 0.0045,
                 std_y: float = 0.01,
                 cov: float = 100000) -> None:

        # State Matrix
        self.S = np.array([xinit, 0, 0, yinit, 0, 0])
        self.dt = 1 / fps

        # State Transition Model
        # Here, we assume that the model follow Newtonian Kinematics
        self.F = np.array([[1, self.dt, 0.5 * (self.dt * self.dt), 0, 0, 0],
                           [0, 1, self.dt, 0, 0, 0], [0, 0, 1, 0, 0, 0],
                           [0, 0, 0, 1, self.dt, 0.5 * self.dt * self.dt],
                           [0, 0, 0, 0, 1, self.dt], [0, 0, 0, 0, 0, 1]])

        self.std_a = std_a

        # Process Noise
        self.Q = np.array([
            [
                0.25 * self.dt * self.dt * self.dt * self.dt, 0.5 * self.dt *
                self.dt * self.dt, 0.5 * self.dt * self.dt, 0, 0, 0
            ],
            [
                0.5 * self.dt * self.dt * self.dt, self.dt * self.dt, self.dt,
                0, 0, 0
            ], [0.5 * self.dt * self.dt, self.dt, 1, 0, 0, 0],
            [
                0, 0, 0, 0.25 * self.dt * self.dt * self.dt * self.dt,
                0.5 * self.dt * self.dt * self.dt, 0.5 * self.dt * self.dt
            ],
            [
                0, 0, 0, 0.5 * self.dt * self.dt * self.dt, self.dt * self.dt,
                self.dt
            ], [0, 0, 0, 0.5 * self.dt * self.dt, self.dt, 1]
        ]) * self.std_a * self.std_a

        self.std_x = std_x
        self.std_y = std_y

        # Measurement Noise
        self.R = np.array([[self.std_x * self.std_x, 0],
                           [0, self.std_y * self.std_y]])

        self.cov = cov

        # Estimate Uncertainity
        self.P = np.array([[self.cov, 0, 0, 0, 0, 0],
                           [0, self.cov, 0, 0, 0, 0],
                           [0, 0, self.cov, 0, 0, 0],
                           [0, 0, 0, self.cov, 0, 0],
                           [0, 0, 0, 0, self.cov, 0],
                           [0, 0, 0, 0, 0, self.cov]])

        # Observation Matrix
        # Here, we are observing X & Y (0th index and 3rd Index)
        self.H = np.array([[1, 0, 0, 0, 0, 0], [0, 0, 0, 1, 0, 0]])

        self.I = np.array([[1, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0],
                           [0, 0, 1, 0, 0, 0], [0, 0, 0, 1, 0, 0],
                           [0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 1]])

        # Predicting the next state and estimate uncertainity
        self.S_pred = None
        self.P_pred = None

        # Kalman Gain
        self.K = None

        # Storing all the State, Kalman Gain and Estimate Uncertainity
        self.S_hist = [self.S]
        self.K_hist = []
        self.P_hist = [self.P]

    def pred_new_state(self):
        self.S_pred = self.F.dot(self.S)

    def pred_next_uncertainity(self):
        self.P_pred = self.F.dot(self.P).dot(self.F.T) + self.Q

    def get_Kalman_gain(self):
        self.K = self.P_pred.dot(self.H.T).dot(
            inv(self.H.dot(self.P_pred).dot(self.H.T) + self.R))
        self.K_hist.append(self.K)

    def state_correction(self, z):
        if z == [None, None]:
            self.S = self.S_pred
        else:
            self.S = self.S_pred + +self.K.dot(z - self.H.dot(self.S_pred))

        self.S_hist.append(self.S)

    def uncertainity_correction(self, z):
        if z != [None, None]:
            self.l1 = self.I - self.K.dot(self.H)
            self.P = self.l1.dot(self.P_pred).dot(self.l1.T) + self.K.dot(
                self.R).dot(self.K.T)
        self.P_hist.append(self.P)

def cost_fun(a, b):
    '''
    Cost function for filter Assignment
    Uses euclidean distance for choosing the filter
    '''

    sm = 0
    for i in range(len(a)):
        sm += (a[i] - b[i])**2
    return sm

import json
import numpy as np
import cv2
from collections import Counter

# Global variables to track coordinate frequencies and stationary object coordinates
global_coord_frequency = {}
stationary_coords = []  # List to store coordinates of detected stationary objects

def group_similar_coordinates(coords, threshold=10):
    """
    Groups coordinates that are within a threshold distance from each other.
    Returns a list of unique coordinates (averaged within the group).
    Also updates the global frequency dictionary.
    """
    grouped_coords = []
    used = [False] * len(coords)

    for i in range(len(coords)):
        if used[i]:
            continue

        # Start a new group with the current coordinate
        current_group = [coords[i]]
        used[i] = True

        for j in range(i + 1, len(coords)):
            # Compute the Euclidean distance between coordinates
            dist = np.linalg.norm(np.array(coords[i]) - np.array(coords[j]))
            if dist < threshold:
                current_group.append(coords[j])
                used[j] = True

        # Average the grouped coordinates
        avg_coord = tuple(np.mean(current_group, axis=0))
        grouped_coords.append((avg_coord, len(current_group)))

        # Update global coordinate frequency
        if avg_coord in global_coord_frequency:
            global_coord_frequency[avg_coord] += len(current_group)
        else:
            global_coord_frequency[avg_coord] = len(current_group)

    return grouped_coords

def identify_stationary_objects(threshold=10):
    """
    Identifies stationary objects by grouping similar coordinates based on frequency of occurrence
    and merging those that are close together.
    """
    global global_coord_frequency, stationary_coords

    # Get the list of coordinates and their frequencies from the global frequency dictionary
    coords_with_freq = list(global_coord_frequency.items())

    def group_coordinates_by_proximity(coords_with_freq, threshold):
        """
        Groups coordinates in the global frequency dictionary by proximity and sums their frequencies.
        """
        grouped_freq = []
        used = [False] * len(coords_with_freq)

        for i in range(len(coords_with_freq)):
            if used[i]:
                continue

            current_group = [coords_with_freq[i][0]]  # Start a new group with the current coordinate
            total_freq = coords_with_freq[i][1]  # Initialize total frequency with current frequency
            used[i] = True

            for j in range(i + 1, len(coords_with_freq)):
                # Compute the Euclidean distance between the coordinates
                dist = np.linalg.norm(np.array(coords_with_freq[i][0]) - np.array(coords_with_freq[j][0]))
                if dist < threshold:
                    current_group.append(coords_with_freq[j][0])
                    total_freq += coords_with_freq[j][1]
                    used[j] = True

            # Average the grouped coordinates
            avg_coord = tuple(np.mean(current_group, axis=0))
            grouped_freq.append((avg_coord, total_freq))

        return grouped_freq

    # Group the coordinates by proximity
    grouped_coords_with_freq = group_coordinates_by_proximity(coords_with_freq, threshold)

    # Define a threshold for considering an object stationary based on frequency
    stationary_threshold = 25  # You can adjust this value

    # Find coordinates that occur above the threshold and add to stationary_coords
    stationary_coords = [(coord,freq) for coord, freq in grouped_coords_with_freq if freq > stationary_threshold]

    return stationary_coords

def is_close_to_blacklist(coord, black_list, threshold=1):
    for black_coord in black_list:
        distance = np.sqrt((coord[0] - black_coord[0])**2 + (coord[1] - black_coord[1])**2)
        if distance <= threshold:
            return True
    return False

def real_time_detection_and_tracking(frames):
    global global_coord_frequency, stationary_coords

    fps = 60
    print(f"FPS: {fps}")

    # Initialize Kalman filter (assuming one object for now)
    # filter_multi = [KalmanFilter(fps=fps, xinit=60, yinit=150, std_x=0.000025, std_y=0.0001)]

    # Set up the video writer for saving the result
    frame_height, frame_width = frames[0].shape[:2]
    out = cv2.VideoWriter('garbage/realtime_tracking_kalman.mp4', cv2.VideoWriter_fourcc(*'mp4v'), fps, (frame_width, frame_height))

    # Dictionary to store tracking data
    tracking_data = {}
    coord_counter = Counter()  # Directly maintain a counter for coordinates
    frame_count = 0

    black_list = [(1894.7992769129137, 303.175568075741), (2333.0154160860784, 1482.0646242436044), (1008.7924158432904, 313.01178965849033)]
    lastx = None
    lasty = None
    lastframeno = None

    listt = {}
    speed_history = []
    shuttle_coordinates_frames = []

    for frame in frames:
        # Run object detection on the current frame (replace with your model inference)
        print(frame_count)
        results = model([frame])

        # Assuming YOLO model results
        boxes = results[0].boxes.xyxy.cpu().numpy()  # Get the bounding boxes
        class_ids = results[0].boxes.cls.cpu().int().numpy()  # Get the class IDs
        scores = results[0].boxes.conf.cpu().numpy()  # Get the confidence scores

        # Convert detection results into a DataFrame
        df_current = pd.DataFrame({
            'xmin': boxes[:, 0],
            'ymin': boxes[:, 1],
            'xmax': boxes[:, 2],
            'ymax': boxes[:, 3],
            'class_id': class_ids,
            'confidence': scores
        })

        print(df_current)

        # Initialize a list to collect the current frame's coordinates for grouping
        current_coords = []
        if frame_count not in listt:
            listt[frame_count] = []

        for _, row in df_current.iterrows():
            coord = [(row['xmin'] + row['xmax']) / 2, (row['ymin'] + row['ymax']) / 2]  # Object center coordinates

            # Only track specific class (e.g., class_id == 0 for a ball/shuttlecock)
            if row['class_id'] == 0:
                if not is_close_to_blacklist(coord, black_list, threshold=15):
                    current_coords.append(coord)

                    if lastx is None:
                        speed = 0
                    else:
                        speed = np.sqrt((coord[0] - lastx) ** 2 + (coord[1] - lasty) ** 2) / (frame_count - lastframeno)
                    listt[frame_count].append({
                        'x_center': coord[0],
                        'y_center': coord[1],
                        'speed': speed
                    })
                    print(coord[0], coord[1], speed)
                    lastx = coord[0]
                    lasty = coord[1]
                    lastframeno = frame_count

        for frame_count, detections in listt.items():
           if len(detections) == 1:
              speed_history.append(detections[0]['speed'])
              if len(speed_history) > 5:  # You can adjust the window size
                        speed_history.pop(0)
              smoothed_speed = np.mean(speed_history)
              tracking_data[f"{frame_count}"] = {
                  'x_center': detections[0]['x_center'],
                  'y_center': detections[0]['y_center'],
                  'smoothened_speed': smoothed_speed
              }
           else:
                tracking_data[f"{frame_count}"] = {
                    'x_center': None,
                    'y_center': None,
                    'smoothened_speed': None
                }

        # Combine previous frequencies with current frame's coordinates
        grouped_coords = group_similar_coordinates(current_coords, threshold=100)

        # Clear coord_counter and update it with the grouped coordinates
        coord_counter.clear()
        for coord, count in grouped_coords:
            coord_counter[coord] += count

        shuttle_coordinates_frames.append(current_coords)
        print("cordinates: ")
        print(current_coords)

        # Visualize the tracking (optional)
        # tmp_img = frame.copy()
        # dummy = 15
        # for x, y in current_coords:
        #     cv2.rectangle(tmp_img, (int(x)-dummy, int(y)-dummy),
        #                   (int(x)+dummy, int(y)+dummy), (0, 255, 0), 2)
        #
        # dummy = 20
        # for x, y in black_list:
        #     cv2.rectangle(tmp_img, (int(x)-dummy, int(y)-dummy),
        #                   (int(x)+dummy, int(y)+dummy), (0, 140, 255), 5)
        #
        #     font = cv2.FONT_HERSHEY_SIMPLEX
        #     cv2.putText(tmp_img, 'stationary', (int(x)-dummy, int(y)-dummy - 10), font, 1, (0, 140, 255), 3)
        #
        # cv2.imwrite("garbage/tmp_img.jpg", tmp_img)
        # out.write(tmp_img)

        # Increment frame count
        print(frame_count)
        frame_count += 1

    out.release()
    cv2.destroyAllWindows()

    # Save tracking data to a JSON file
    with open('result/shuttle_data/shuttle_data.json', 'w') as json_file:
        json.dump(tracking_data, json_file, indent=4)

    # Identify stationary objects based on frequency
    stationary_coords = identify_stationary_objects()
    print("Stationary coordinates detected:")
    print(stationary_coords)

    return tracking_data

# Example usage
# real_time_detection_and_tracking("video.mp4", "shuttle_data.json")

# real_time_detection_and_tracking('../utils/footages/12sec.mp4')

def draw_shuttle_predictions(frames, tracking_data):
    output_frames = []
    i = 0
    for frame in frames:
        output_frame = draw_shuttle_predictions_frame(frame, tracking_data, i)
        i = i + 1

        output_frames.append(output_frame)

    return output_frames


def draw_shuttle_predictions_frame(frame, tracking_data, i):
    dummy = 15

    # Check if the current frame number is in tracking_data
    if i in tracking_data:
        # Get the x and y coordinates from tracking_data
        x = tracking_data[i]['x_center']
        y = tracking_data[i]['y_center']
        speed = tracking_data[i]['smoothened_speed']

        print("lol")
        print(x, y)
        # Draw the bounding box around the detected object
        cv2.rectangle(frame, (int(x) - dummy, int(y) - dummy),
                      (int(x) + dummy, int(y) + dummy), (0, 255, 0), 2)

        # Display the speed on the frame
        speed_text = f"Speed: {speed:.2f}"
        cv2.putText(frame, speed_text, (int(x) - dummy, int(y) - dummy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 140, 255), 3)

    # Return the frame with shuttle predictions drawn
    return frame

def interpolate_shuttle_tracking(tracking_data):
    # with open(json_path, 'r') as file:
    #     tracking_data = json.load(file)

    # Extract the x and y coordinates for each frame from the JSON data
    shuttle_coordinates_frames = [
        (frame_data['x_center'], frame_data['y_center'], frame_data['smoothened_speed'])
        for frame_data in tracking_data.values()
    ]

    print(len(shuttle_coordinates_frames))

    # Convert the coordinates into a pandas DataFrame
    df_shuttle_positions = pd.DataFrame(shuttle_coordinates_frames, columns=['x_center', 'y_center', 'smoothened_speed'])

    # Interpolate missing values
    df_shuttle_positions = df_shuttle_positions.interpolate(method='linear')
    df_shuttle_positions = df_shuttle_positions.bfill()

    tracking_data = df_shuttle_positions.to_dict(orient='index')

    with open('result/shuttle_data/shuttle_data.json', 'w') as json_file:
        json.dump(tracking_data, json_file, indent=4)

    return tracking_data

def identify_stationary_objects(threshold=10):
    """
    Identifies stationary objects by grouping similar coordinates based on frequency of occurrence
    and merging those that are close together.
    """
    global global_coord_frequency, stationary_coords

    # Get the list of coordinates and their frequencies from the global frequency dictionary
    coords_with_freq = list(global_coord_frequency.items())

    def group_coordinates_by_proximity(coords_with_freq, threshold):
        """
        Groups coordinates in the global frequency dictionary by proximity and sums their frequencies.
        """
        grouped_freq = []
        used = [False] * len(coords_with_freq)

        for i in range(len(coords_with_freq)):
            if used[i]:
                continue

            current_group = [coords_with_freq[i][0]]  # Start a new group with the current coordinate
            total_freq = coords_with_freq[i][1]  # Initialize total frequency with current frequency
            used[i] = True

            for j in range(i + 1, len(coords_with_freq)):
                # Compute the Euclidean distance between the coordinates
                dist = np.linalg.norm(np.array(coords_with_freq[i][0]) - np.array(coords_with_freq[j][0]))
                if dist < threshold:
                    current_group.append(coords_with_freq[j][0])
                    total_freq += coords_with_freq[j][1]
                    used[j] = True

            # Average the grouped coordinates
            avg_coord = tuple(np.mean(current_group, axis=0))
            grouped_freq.append((avg_coord, total_freq))

        return grouped_freq

    # Group the coordinates by proximity
    grouped_coords_with_freq = group_coordinates_by_proximity(coords_with_freq, threshold)

    # Define a threshold for considering an object stationary based on frequency
    stationary_threshold = 10  # You can adjust this value

    # Find coordinates that occur above the threshold and add to stationary_coords
    stationary_coords = [(coord,freq) for coord, freq in grouped_coords_with_freq if freq > stationary_threshold]

    return stationary_coords
identify_stationary_objects()

print(stationary_coords)