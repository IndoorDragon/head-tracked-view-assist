# Head-Tracked View Assist (Blender Add-on)

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Blender](https://img.shields.io/badge/Blender-4.x-orange)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Platform](https://img.shields.io/badge/Platform-Linux-lightgrey)
![Platform](https://img.shields.io/badge/Platform-macOS-black)

Head-Tracked View Assist is a Blender add-on that enables hands-free viewport navigation using real-time head tracking from a standard webcam.

It combines:
- Blender add-on (UI + viewport control), and
- Bundled Tracker executable (OpenCV + MediaPipe) that sends motion data to Blender over localhost UDP.

### Depth Perspective Demo
![Head-Tracked View Assist Depth Perspective Demo](assets/depthperspective.gif)

### Tracker Demo
![Head-Tracked View Assist Tracker Demo](assets/viewassistgif.gif)

### Blender Add-On UI
![Head-Tracked View Assist Add-On UI](assets/Blender_Addon_UI.png)


## Features
- Real-time head tracking using a webcam  
- Smooth viewport yaw/pitch + zoom  
- Adjustable sensitivity and smoothing  
- Multi-viewport support  
- One-click tracker launch from Blender  
- Launch tracker with preview window or run silently in the background  
- Prevents multiple tracker instances from running simultaneously  
- No external Python installation required  

## Requirements
- Blender 4.x (Windows)
- Windows / Linux/ macOS
- Webcam

## Download / Install
1. Go to **Releases** and download the latest ZIP asset (e.g. `head_tracked_view_assist_v0.1.0.zip`).
2. In Blender: **Edit → Preferences → Add-ons → Install…**
3. Select the downloaded ZIP.
4. Enable the add-on.
5. Open the 3D View sidebar (**N**) → **View Assist** tab.

## Usage
1. Click **Launch Tracker** (allow webcam access if prompted).
2. Click **Start** to enable head-tracked view assist.
3. Move your head to control the viewport.
4. Use **Stop Tracker** to close the tracker gracefully.

## Tracker Launch Modes

The tracker can be launched in two ways:

**Preview Mode**
- Opens a window showing the webcam feed
- Useful for setup and calibration
- Allows visual confirmation that tracking is working

**Background Mode**
- Runs silently without any visible window
- Ideal for normal use while working in Blender
- Reduces screen clutter and system distraction

Only one tracker instance can run at a time.

### Controls
| Motion | Effect |
|---|---|
| Head left/right | Yaw rotation |
| Head up/down | Pitch rotation |
| Move closer/farther | Zoom |

## How it works
**Data flow:**
Webcam → OpenCV → MediaPipe → Motion Extraction → UDP → Blender → Viewport Update

**Localhost ports:**
- Pose data: `127.0.0.1:5005`
- Control channel: `127.0.0.1:5006`

No external network access is required.

## Files created at runtime
- `config.json`: stores persistent tracker settings (ex: camera index)
- `tracker_pid.txt`: used for safe shutdown / process management

## Privacy & Security
- Webcam data is processed locally only
- No images are stored or transmitted externally
- UDP communication is limited to localhost

## Troubleshooting
**Tracker does not start**
- Ensure antivirus allows webcam access
- Verify the webcam is not used by another application

**Port already in use**
- You may have multiple tracker instances running
- Stop the existing tracker before launching again, or restart Blender

**No face detected**
- Improve lighting
- Ensure face is visible to camera
- Verify the correct camera is selected

**Preview window shows wrong camera or black screen**
- Your system may have multiple camera devices (built-in webcam, USB webcam, virtual cameras, etc.)
- The tracker may open a different device than expected
- In the Preview window, press:

  - **N** → Next camera device  
  - **P** → Previous camera device  

- Cycle until the correct webcam feed appears
- The selected camera is saved for future launches


## Depth Perspective Demo Scene

A **Depth Perspective demo `.blend` scene** is included in the **Releases page**.

This scene demonstrates how head tracking can create a **depth illusion effect** within Blender.

The demo scene includes:
- a grid room environment
- a centered object for reference
- shader-based grid walls that enhance the depth effect

**Note**

Because screen sizes and aspect ratios vary between systems, the demo scene may require **manual adjustment**.

You can customize the scene by:

- Adjusting the **grid spacing in the Shader Editor**
- Scaling the room geometry
- Importing your **own models into the scene**

This allows you to experiment with the depth effect using your own assets.


## License

This project is licensed under the MIT License.  
See the LICENSE file for details.
