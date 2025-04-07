set -e

ctags *.py
# python unit.py ; exit
python td2e2.py
echo ; echo ; cat td2e2-jlcpcb-bom.csv
echo ; echo ; cat td2e2-jlcpcb-pnp.csv
# python wordclock.py
# python clock2.py
# qiv out.png
# python clockpwr.py
# python scanalyzer2.py
# python ezbake.py

for W in $(xdotool search --onlyvisible --name Gerbv)
do
  xdotool key --window $W F5
done
