PLIST  := com.cybercussion.dolly
PLIST_SRC := $(CURDIR)/$(PLIST).plist
PLIST_DST := $(HOME)/Library/LaunchAgents/$(PLIST).plist

.PHONY: install uninstall start stop restart status logs tail run

install:
	ln -sf $(PLIST_SRC) $(PLIST_DST)
	@echo "Plist symlinked → $(PLIST_DST)"

uninstall: stop
	rm -f $(PLIST_DST)
	@echo "Plist removed."

start:
	launchctl load $(PLIST_DST)
	@echo "Dolly started."

stop:
	-launchctl unload $(PLIST_DST)
	@echo "Dolly stopped."

restart: stop start

status:
	@launchctl list | grep $(PLIST) || echo "Not running."

run:
	$(CURDIR)/.venv/bin/python $(CURDIR)/run.py

logs:
	@cat dolly.log

tail:
	@tail -f dolly.log
