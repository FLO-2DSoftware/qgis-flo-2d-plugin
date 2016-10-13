THIS_DIR=./
SOURCE_DIR=$(THIS_DIR)../flo2d
USER_HELP_DIR=$(THIS_DIR)../docs/user
DEV_HELP_DIR=$(THIS_DIR)../docs/dev 

PLUGINNAME = flo2d

HELP = $(USER_HELP_DIR)/build/html/
QGISDIR=.qgis2

default: deploy

deploy: derase doc
	@echo
	@echo "------------------------------------------"
	@echo "Deploying plugin to your .qgis2 directory."
	@echo "------------------------------------------"
	# The deploy  target only works on unix like operating system where
	# the Python plugin directory is located at:
	# $HOME/$(QGISDIR)/python/plugins
	mkdir -p $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)
	cd $(SOURCE_DIR); echo y | pb_tool deploy
	rm -rf $(HOME)/$(QGISDIR)/python/plugins/$(PLUGINNAME)/help
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
	
