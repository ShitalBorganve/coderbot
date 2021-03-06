import time
import copy
from threading import Thread, Lock

import SimpleCV

CAMERA_REFRESH_INTERVAL=0.3
CAMERA_DELAY_INTERVAL=0.3
MAX_IMAGE_AGE = 0.0

class Camera(Thread):

  _instance = None
  _cam_props = {"width":640, "height":480}
  _cam_off_img = SimpleCV.Image("coderdojo-logo.png")
  _warp_corners_1 = [(0, -120), (640, -120), (380, 480), (260, 480)]
  _warp_corners_2 = [(0, -60), (320, -60), (190, 240), (130, 240)]
  _warp_corners_4 = [(0, -30), (160, -30), (95, 120), (65, 120)]
  stream_port = 8090

  @classmethod
  def get_instance(cls):
    if not cls._instance:
      cls._instance = Camera()
      cls._instance.start()
    return cls._instance

  def __init__(self):
    print "starting camera"
    self._camera = SimpleCV.Camera(prop_set=self._cam_props)
    self._streamer = SimpleCV.JpegStreamer("0.0.0.0:"+str(self.stream_port), st=0.1)
    self._cam_off_img.save(self._streamer)
    self._run = True
    self._image_time = 0
    self._image_lock = Lock()
    super(Camera, self).__init__()

  def run(self):
    while self._run:
      ts = time.time()
      #print "run.1"
      self._image_lock.acquire()
      self._image = self._camera.getImage()
      #print "run.2: " + str(time.time()-ts)
      if time.time() - self._image_time > CAMERA_REFRESH_INTERVAL:
        self.save_image(self._image)
        #print "run.3: " + str(time.time()-ts)
      self._image_lock.release()
      time.sleep(CAMERA_REFRESH_INTERVAL)
    
  def get_image(self, maxage = MAX_IMAGE_AGE):
    return self._camera.getImage()

  def save_image(self, image):
    image.save(self._streamer)
    self._image_time=time.time()

  def exit(self):
    self._run = False
    self.join()

  def calibrate(self):
    img = self._camera.getImage()
    self._background = img.hueHistogram()[-1]
        
  def find_line(self):
    self._image_lock.acquire()
    img = self.get_image(0)
    img.drawRectangle(0,200,640,40)
    img.drawRectangle(240,200,160,40, color=(0,0,255))
    cropped = img.crop(0, 200, 640, 40)
    blobs = cropped.findBlobs(minsize=800, maxsize=4000)
    coordX = 50
    if blobs and len(blobs):
      line = blobs[-1]
      img.drawRectangle(line.minRect()[0][0], 200, line.width(), line.height(), color=(0,255,0))
      coordX = (line.coordinates()[0] * 100) / cropped.width
    
    self._image_lock.release()
    return coordX

    
  def find_signal(self):
    #print "signal"
    angle = None
    ts = time.time()
    self._image_lock.acquire()
    img = self.get_image(0)
    #print "signal.get_image: " + str(time.time() - ts)
    warped = img.resize(320).warp(self._warp_corners_2).resize(640)
    #print "signal.warp: " + str(time.time() - ts)
    cropped = warped.crop(260, 160, 120, 320)

    binarized = cropped.binarize()

    blobs = binarized.findBlobs(minsize=3000, maxsize=4000)
    #print blobs
    print "signal.blobs: " + str(time.time() - ts)
    signal = binarized
    coordY = 60
    if blobs and len(blobs):
      blobs.draw()
      signals = blobs.filter([b.isSquare() for b in blobs]) 
      #print signals
      if signals:
        signal = signals.sortDistance((320, 480))[0].crop().crop(8,8,46,46)
        #print "found signal: " + str(signal)
        lines = signal.findLines(threshold=10, minlinelength=10, maxlinegap=2, cannyth1=50, cannyth2=100)
        #print "lines: " + str(lines)
        if lines and len(lines):
          lines = lines.sortLength()
        
          center_line = lines[-1]
          center_line.draw()

          #print "center_line: " + str(center_line.length())

          angle = center_line.angle()
          #print "angle raw: " + str(angle)
          if angle < 0.0:
            angle = angle + 360
          if (((angle < 45.0 or angle > 315.0) and (center_line.coordinates()[0] < (signal.width / 2))) or
             ((angle > 45.0 and angle < 135.0)  and (center_line.coordinates()[1] > (signal.height / 2))) or
             ((angle > 135.0 and angle < 225.0) and (center_line.coordinates()[0] > (signal.width / 2))) or
             ((angle > 225.0 and angle < 315.0)  and (center_line.coordinates()[1] < (signal.height / 2)))):
            angle = angle + 180
          if angle > 360.0:
            angle = angle - 360
          
          img.drawText("signal found pointing at " + str(angle), 0, 0, fontsize=32 )
          #print "angle final: " + str(angle)
        else:
          angle = -1
          img.drawText("stop signal found", 0, 0, fontsize=32 )

    self.save_image(img)
    self._image_lock.release()
    #print "signal: " + str(time.time() - ts)
    return angle

  def find_face(self):
    print "face"
    faceX = None
    ts = time.time()
    self._image_lock.acquire()
    img = self.get_image(0)
    faces = img.resize(160).findHaarFeatures('face.xml')
    print "face.findHaar: " + str(time.time() - ts)
    if faces is not None and len(faces):
      # Get the largest face 
      faces = faces.sortArea() 
      bigFace = faces[-1]
      # Draw a green box around the face 
      #bigFace.draw()
      faceX = (bigFace.coordinates()[0] * 100) / 80

    self.save_image(img)
    self._image_lock.release()
    print "face: " + str(time.time() - ts)
    return faceX

  def path_ahead(self):
    print "path ahead"
    ts = time.time()
    self._image_lock.acquire()
    img = self.get_image(0)
    print "path_ahead.get_image: " + str(time.time() - ts)
    warped = img.resize(160).warp(self._warp_corners_4).resize(640)
    print "path_ahead.warp: " + str(time.time() - ts)
    #ar_layer = SimpleCV.DrawingLayer((warped.width, warped.height))
    #ar_layer.rectangle((260,120),(120,320), color=(0,255,0))
    cropped = warped.crop(260, 160, 120, 320)
    control = cropped.crop(0, 280, 160, 40)

    control_color = control.meanColor()
    color_distance = cropped.dilate().colorDistance(control_color)

    control_hue = control.getNumpy().mean()
    #hue_distance = cropped.dilate().hueDistance(control_hue)

    print "path_ahead.crop: " + str(time.time() - ts)
    #control_hue = control_hue - 20 if control_hue > 127 else control_hue + 20
    #binarized = cropped.dilate().binarize(control_hue)
    #binarized = cropped.dilate().binarize().invert()
    control_hue = control_hue - 10
    binarized = color_distance.binarize(control_hue).invert()
    print "path_ahead.binarize: " + str(time.time() - ts)
    blobs = binarized.findBlobs(minsize=1000, maxsize=(cropped.width*cropped.height)-2000)
    print "path_ahead.blobs: " + str(time.time() - ts)
    coordY = 60
    if blobs and len(blobs):
      print blobs
      obstacle = blobs.sortDistance(point=(60,320))[0]
      print "path_ahead.sortdistnace: " + str(time.time() - ts)
      #dw_x = 260 + obstacle.coordinates()[0] - (obstacle.width()/2)
      #dw_y = 160 + obstacle.coordinates()[1] - (obstacle.height()/2) 
      #img.drawRectangle(dw_x, dw_y, obstacle.width(), obstacle.height(), color=(255,0,0))
      coordY = 60 - (((obstacle.coordinates()[1]+(obstacle.height()/2)) * 48) / cropped.height) 
      #print obstacle.coordinates()[1]+(obstacle.height()/2)
      #ar_layer.centeredRectangle(obstacle.coordinates(), (obstacle.width(), obstacle.height()))
      #warped.addDrawingLayer(ar_layer)
      #warped.applyLayers()
      #self.save_image(warped.warp(self._unwarp_corners), expire=10)

    img.drawText("path ahead clear for " + str(coordY) + " cm", 0, 0, fontsize=32 )
    print "path_ahead.drawtext: " + str(time.time() - ts)
    self.save_image(img)
    print "path_ahead.save_image: " + str(time.time() - ts)
    self._image_lock.release()
    print "path_ahead: " + str(time.time() - ts)
    return coordY

  def find_code(self):
    #print "code"
    code_data = None
    ts = time.time()
    self._image_lock.acquire()
    img = self.get_image(0)
    #print "signal.get_image: " + str(time.time() - ts)
    warped = img.resize(320).warp(self._warp_corners_2).resize(640)
    #print "code.warp: " + str(time.time() - ts)
    cropped = warped.crop(260, 160, 120, 320)

    barcode = cropped.findBarcode()
    if barcode:
      code_data = barcode.data
      img.drawText("code found: " + data, 0, 0, fontsize=32 )
    self.save_image(img)
    self._image_lock.release()
    #print "code: " + str(time.time() - ts)
    return code_data
    
  def find_logo(self):
    #print "logo"
    logo_y = None
    ts = time.time()
    self._image_lock.acquire()
    img = self.get_image(0)
    #print "logo.get_image: " + str(time.time() - ts)
    warped = img.resize(320).warp(self._warp_corners_2).resize(640)
    #print "logo.warp: " + str(time.time() - ts)
    cropped = warped.crop(260, 160, 120, 320)

    logo = img.findKeypointMatch(self._cam_off_img)
    if logo:
      #logo = logos[-1]
      x, y = logo.coordinates()
      print "found logo at: " + str(x) + " " + str(y)
      logo_y = 60 - ((y * 48) / cropped.height) 
      img.drawText("logo found at: " + str(logo.coordinates()), 0, 0, fontsize=32 )
    self.save_image(img)
    self._image_lock.release()
    #print "code: " + str(time.time() - ts)
    return logo_y 
    
  def sleep(self, elapse):
    print "sleep"
    time.sleep(elapse)

