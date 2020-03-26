#version 3.6;

#include "colors.inc"

#default{finish{ambient 0.01}}
#global_settings{assumed_gamma 1.0 max_trace_level 5}

sky_sphere {
  pigment { color MidnightBlue }
}


 #default {
   texture {
     pigment { rgb <1,0,0> }
     finish { ambient 0.4 }
   }
 }

#include "dazzler.gtl.pov"

light_source{<-1000, 1000, 500> color rgb<1.5, 1.3, 1.2>}
light_source{< 1000, -1000, -500> color rgb<0.2, 0.5, 1.0>*0.15}

camera{
  location <0, 0, -400>
  up y * (image_height / image_width)
  right x
  sky y
  look_at <25, 25, 0>
  angle 28
}
