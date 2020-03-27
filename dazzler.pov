#version 3.6;

#include "colors.inc"
#include "metals.inc"

#default{finish{ambient 0.01}}
#global_settings{assumed_gamma 1.0 max_trace_level 5}

sky_sphere {
  pigment { color MidnightBlue }
}


union {
  #include "dazzler.sub.pov"
  texture {
    pigment { color rgbf<0.0, 0.0, 0.0, 1.0> }
    finish {
      reflection { 0.10 }
      specular 0.5
      roughness .006
    }
    normal { bumps 0.005 }
  }
}

union {
  #include "dazzler.gtl.pov"
  rotate <90, 0, 0>
  translate <0 1.030 0>
  texture {
   pigment {P_Copper2}
   finish {F_MetalA }
  }
}

union {
  #include "dazzler.gto.pov"
  rotate <90, 0, 0>
  translate <0 1.031 0>
  texture {
   pigment {White}
  }
}

light_source{<80, 180, 200> color rgb<.3 .3 .4>}
light_source{<25, 80, 80> color rgb<1.0 0.8 .4>}

camera{
  location <0, 100, -100>
  up y * (image_height / image_width)
  right x
  sky y
  look_at <25, 0, 20>
  angle 23

  focal_point < 25,0,20>
  aperture 4
  blur_samples 20
}
