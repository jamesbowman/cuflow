python dazzler.py
for W in $(xdotool search --onlyvisible --name Gerbv)
do
  xdotool key --window $W F5
done
