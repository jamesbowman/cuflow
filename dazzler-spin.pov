#version 3.6;

#include "scene-dazzler.pov"

camera{
  location <0, 100, -100>
  up y * (image_height / image_width)
  right x
  sky y
  look_at <25, 0, 20>
  angle 23 - 1 * clock

  focal_point <25, 0, 20>
  aperture 7
  blur_samples 8
}
