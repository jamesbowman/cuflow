PICKLE_FILES := $(wildcard ../*.pickle)
PNG_FILES    := $(notdir $(PICKLE_FILES:.pickle=.png))

all: $(PNG_FILES)

%.png: ../%.pickle mktiles.py
	python mktiles.py $<

clean:
	rm -f $(PNG_FILES)
