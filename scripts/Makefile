#Add iso code for any locales you want to support here (space separated)
# default is no locales
# LOCALES = af
LOCALES =

# If locales are enabled, set the name of the lrelease binary on your system. If
# you have trouble compiling the translations, you may have to specify the full path to
# lrelease
#LRELEASE = lrelease
#LRELEASE = lrelease-qt4

# dir
THIS_DIR=./
SOURCE_DIR=$(THIS_DIR)../flo2d
USER_HELP_DIR=$(THIS_DIR)../docs/user
DEV_HELP_DIR=$(THIS_DIR)../docs/dev 
I18N_DIR=$(SOURCE_DIR)/i18n

# translation
SOURCES = \
	$(SOURCE_DIR)/__init__.py \
	$(SOURCE_DIR)/flo2d.py \
	$(SOURCE_DIR)/flo2d_dialog.py \
	$(SOURCE_DIR)/user_communication.py \
	$(SOURCE_DIR)/utils.py \
	$(SOURCE_DIR)/flo2dgeopackage.py \
	$(SOURCE_DIR)/flo2d_parser.py \
	$(SOURCE_DIR)/layers.py \
	$(SOURCE_DIR)/errors.py

PLUGINNAME = flo2d

PY_FILES = \
	$(SOURCE_DIR)/__init__.py \
	$(SOURCE_DIR)/flo2d.py \
	$(SOURCE_DIR)/flo2d_dialog.py \
	$(SOURCE_DIR)/user_communication.py \
	$(SOURCE_DIR)/utils.py \
	$(SOURCE_DIR)/flo2dgeopackage.py \
	$(SOURCE_DIR)/flo2d_parser.py \
	$(SOURCE_DIR)/layers.py \
	$(SOURCE_DIR)/errors.py

UI_FILES = $(SOURCE_DIR)/flo2d_dialog_base.ui

EXTRAS = $(SOURCE_DIR)/metadata.txt \
	 $(SOURCE_DIR)/db_structure.sql

COMPILED_RESOURCE_FILES = $(SOURCE_DIR)/resources.py

PEP8EXCLUDE=$(SOURCE_DIR)/pydev,$(SOURCE_DIR)/resources.py,$(SOURCE_DIR)/conf.py,$(SOURCE_DIR)/third_party,$(SOURCE_DIR)/ui


#################################################
# Normally you would not need to edit below here
#################################################

HELP = $(USER_HELP_DIR)/build/html

PLUGIN_UPLOAD = $(c)/plugin_upload.py

RESOURCE_SRC=$(shell grep '^ *<file' $(SOURCE_DIR)/resources.qrc | sed 's@</file>@@g;s/.*>//g' | tr '\n' ' ')

QGISDIR=.qgis2

default: compile

compile: $(COMPILED_RESOURCE_FILES)

%.py : %.qrc $(RESOURCES_SRC)
	pyrcc4 -o $*.py  $<

%.qm : %.ts
	$(LRELEASE) $<
	
test: compile transcompile
	@echo
	@echo "----------------------"
	@echo "Test Suite            "
	@echo "----------------------"
	@# Preceding dash means that make will continue in case of errors
	@-export PYTHONPATH=$(THIS_DIR)/..:$(PYTHONPATH); \
		export QGIS_DEBUG=0; \
		export QGIS_LOG_FILE=/dev/null; \
		nosetests -v test --cover-package=flo2d --with-coverage --cover-xml --cover-xml-file=nose_coverage.xml --with-xunit --xunit-file=nosetests.xml || true

deploy: compile doc transcompile
	@echo
	@echo "------------------------------------------"
	@echo "Deploying plugin to your .qgis2 directory."
	@echo "------------------------------------------"
	# The deploy  target only works on unix like operating system where
	# the Python plugin directory is located at:
	# $HOME/$(QGISDIR)/python/plugins
	mkdir -p $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)
	cp -vf $(PY_FILES) $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)
	cp -vf $(UI_FILES) $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)
	cp -vf $(COMPILED_RESOURCE_FILES) $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)
	cp -vf $(EXTRAS) $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)
	cp -vfr $(I18N_DIR) $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)
	cp -vfr $(HELP) $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/help

# The dclean target removes compiled python files from plugin directory
# also deletes any .git entry
dclean:
	@echo
	@echo "-----------------------------------"
	@echo "Removing any compiled python files."
	@echo "-----------------------------------"
	find $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME) -iname "*.pyc" -delete
	find $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME) -iname ".git" -prune -exec rm -Rf {} \;


derase:
	@echo
	@echo "-------------------------"
	@echo "Removing deployed plugin."
	@echo "-------------------------"
	rm -Rf $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)

zip: deploy dclean
	@echo
	@echo "---------------------------"
	@echo "Creating plugin zip bundle."
	@echo "---------------------------"
	# The zip target deploys the plugin and creates a zip file with the deployed
	# content. You can then upload the zip file on http://plugins.qgis.org
	rm -f $(PLUGINNAME).zip
	cd $(HOME)/$(QGISDIR)/python/plugins; zip -9r $(CURDIR)/$(PLUGINNAME).zip $(PLUGINNAME)

package: compile
	# Create a zip package of the plugin named $(PLUGINNAME).zip.
	# This requires use of git (your plugin development directory must be a
	# git repository).
	# To use, pass a valid commit or tag as follows:
	#   make package VERSION=Version_0.3.2
	@echo
	@echo "------------------------------------"
	@echo "Exporting plugin to zip package.	"
	@echo "------------------------------------"
	rm -f $(PLUGINNAME).zip
	git archive --prefix=$(PLUGINNAME)/ -o $(PLUGINNAME).zip $(VERSION)
	echo "Created package: $(PLUGINNAME).zip"

upload: zip
	@echo
	@echo "-------------------------------------"
	@echo "Uploading plugin to QGIS Plugin repo."
	@echo "-------------------------------------"
	$(PLUGIN_UPLOAD) $(PLUGINNAME).zip

transup:
	@echo
	@echo "------------------------------------------------"
	@echo "Updating translation files with any new strings."
	@echo "------------------------------------------------"
	@chmod +x $(THIS_DIR)update-strings.sh
	@$(THIS_DIR)update-strings.sh $(LOCALES)

transcompile:
	@echo
	@echo "----------------------------------------"
	@echo "Compiled translation files to .qm files."
	@echo "----------------------------------------"
	@chmod +x $(THIS_DIR)compile-strings.sh
	@$(THIS_DIR)compile-strings.sh $(LRELEASE) $(LOCALES)

transclean:
	@echo
	@echo "------------------------------------"
	@echo "Removing compiled translation files."
	@echo "------------------------------------"
	rm -f $(I18N_DIR)/*.qm

clean:
	@echo
	@echo "------------------------------------"
	@echo "Removing uic and rcc generated files"
	@echo "------------------------------------"
	rm $(COMPILED_UI_FILES) $(COMPILED_RESOURCE_FILES)

doc-all: doc docpdf devdoc devdocpdf

	
doc:
	@echo
	@echo "------------------------------------"
	@echo "Building user documentation         "
	@echo "------------------------------------"
	cd $(USER_HELP_DIR); make html

docpdf:
	@echo
	@echo "------------------------------------"
	@echo "Building user documentation         "
	@echo "------------------------------------"
	cd $(USER_HELP_DIR); make latexpdf
	
devdoc:
	@echo
	@echo "------------------------------------"
	@echo "Building dev documentation         "
	@echo "------------------------------------"
	cd $(DEV_HELP_DIR); make html

devdocpdf:
	@echo
	@echo "------------------------------------"
	@echo "Building dev documentation         "
	@echo "------------------------------------"
	cd $(DEV_HELP_DIR); make latexpdf
	
pylint:
	@echo
	@echo "-----------------"
	@echo "Pylint violations"
	@echo "-----------------"
	@pylint --reports=n --rcfile=pylintrc . || true
	@echo
	@echo "----------------------"
	@echo "If you get a 'no module named qgis.core' error, try sourcing"
	@echo "the helper script we have provided first then run make pylint."
	@echo "e.g. source run-env-linux.sh <path to qgis install>; make pylint"
	@echo "----------------------"


# Run pep8 style checking
#http://pypi.python.org/pypi/pep8
pep8:
	@echo
	@echo "-----------"
	@echo "PEP8 issues"
	@echo "-----------"
	@pep8 --repeat --ignore=E203,E121,E122,E123,E124,E125,E126,E127,E128 --exclude $(PEP8EXCLUDE) . || true
	@echo "-----------"
	@echo "Ignored in PEP8 check:"
	@echo $(PEP8EXCLUDE)
