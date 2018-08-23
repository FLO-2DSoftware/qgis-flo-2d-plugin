<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis hasScaleBasedVisibilityFlag="0" minScale="1e+8" readOnly="0" version="3.2.2-Bonn" maxScale="0">
  <fieldConfiguration>
    <field name="fid">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field name="name">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field name="time_series_fid">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field name="ident">
      <editWidget type="ValueMap">
        <config>
          <Option type="Map">
            <Option name="map" type="List">
              <Option type="Map">
                <Option name="Channel" value="C" type="QString"/>
              </Option>
              <Option type="Map">
                <Option name="Floodplain" value="F" type="QString"/>
              </Option>
            </Option>
          </Option>
        </config>
      </editWidget>
    </field>
    <field name="inoutfc">
      <editWidget type="ValueMap">
        <config>
          <Option type="Map">
            <Option name="map" type="List">
              <Option type="Map">
                <Option name="Inflow" value="0" type="QString"/>
              </Option>
              <Option type="Map">
                <Option name="Outflow" value="1" type="QString"/>
              </Option>
            </Option>
          </Option>
        </config>
      </editWidget>
    </field>
    <field name="note">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field name="geom_type">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field name="bc_fid">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
  </fieldConfiguration>
  <aliases>
    <alias name="" index="0" field="fid"/>
    <alias name="" index="1" field="name"/>
    <alias name="" index="2" field="time_series_fid"/>
    <alias name="" index="3" field="ident"/>
    <alias name="" index="4" field="inoutfc"/>
    <alias name="" index="5" field="note"/>
    <alias name="" index="6" field="geom_type"/>
    <alias name="" index="7" field="bc_fid"/>
  </aliases>
  <excludeAttributesWMS/>
  <excludeAttributesWFS/>
  <defaults>
    <default applyOnUpdate="0" expression="" field="fid"/>
    <default applyOnUpdate="0" expression="" field="name"/>
    <default applyOnUpdate="0" expression="" field="time_series_fid"/>
    <default applyOnUpdate="0" expression="" field="ident"/>
    <default applyOnUpdate="0" expression="" field="inoutfc"/>
    <default applyOnUpdate="0" expression="" field="note"/>
    <default applyOnUpdate="0" expression="" field="geom_type"/>
    <default applyOnUpdate="0" expression="" field="bc_fid"/>
  </defaults>
  <constraints>
    <constraint constraints="3" exp_strength="0" unique_strength="1" notnull_strength="1" field="fid"/>
    <constraint constraints="0" exp_strength="0" unique_strength="0" notnull_strength="0" field="name"/>
    <constraint constraints="0" exp_strength="0" unique_strength="0" notnull_strength="0" field="time_series_fid"/>
    <constraint constraints="0" exp_strength="0" unique_strength="0" notnull_strength="0" field="ident"/>
    <constraint constraints="0" exp_strength="0" unique_strength="0" notnull_strength="0" field="inoutfc"/>
    <constraint constraints="0" exp_strength="0" unique_strength="0" notnull_strength="0" field="note"/>
    <constraint constraints="0" exp_strength="0" unique_strength="0" notnull_strength="0" field="geom_type"/>
    <constraint constraints="0" exp_strength="0" unique_strength="0" notnull_strength="0" field="bc_fid"/>
  </constraints>
  <constraintExpressions>
    <constraint exp="" field="fid" desc=""/>
    <constraint exp="" field="name" desc=""/>
    <constraint exp="" field="time_series_fid" desc=""/>
    <constraint exp="" field="ident" desc=""/>
    <constraint exp="" field="inoutfc" desc=""/>
    <constraint exp="" field="note" desc=""/>
    <constraint exp="" field="geom_type" desc=""/>
    <constraint exp="" field="bc_fid" desc=""/>
  </constraintExpressions>
  <attributeactions>
    <defaultAction value="{00000000-0000-0000-0000-000000000000}" key="Canvas"/>
  </attributeactions>
  <attributetableconfig sortExpression="" actionWidgetStyle="dropDown" sortOrder="0">
    <columns>
      <column width="-1" name="fid" type="field" hidden="0"/>
      <column width="-1" name="name" type="field" hidden="0"/>
      <column width="-1" name="time_series_fid" type="field" hidden="0"/>
      <column width="-1" name="ident" type="field" hidden="0"/>
      <column width="-1" name="inoutfc" type="field" hidden="0"/>
      <column width="-1" name="note" type="field" hidden="0"/>
      <column width="-1" name="geom_type" type="field" hidden="0"/>
      <column width="-1" name="bc_fid" type="field" hidden="0"/>
      <column width="-1" type="actions" hidden="1"/>
    </columns>
  </attributetableconfig>
  <editform tolerant="1"></editform>
  <editforminit/>
  <editforminitcodesource>0</editforminitcodesource>
  <editforminitfilepath></editforminitfilepath>
  <editforminitcode><![CDATA[# -*- coding: utf-8 -*-
"""
QGIS forms can have a Python function that is called when the form is
opened.

Use this function to add extra logic to your forms.

Enter the name of the function in the "Python Init function"
field.
An example follows:
"""
from qgis.PyQt.QtWidgets import QWidget

def my_form_open(dialog, layer, feature):
	geom = feature.geometry()
	control = dialog.findChild(QWidget, "MyLineEdit")
]]></editforminitcode>
  <featformsuppress>0</featformsuppress>
  <editorlayout>generatedlayout</editorlayout>
  <editable>
    <field name="bc_fid" editable="1"/>
    <field name="fid" editable="1"/>
    <field name="geom_type" editable="1"/>
    <field name="ident" editable="1"/>
    <field name="inoutfc" editable="1"/>
    <field name="name" editable="1"/>
    <field name="note" editable="1"/>
    <field name="time_series_fid" editable="1"/>
  </editable>
  <labelOnTop>
    <field name="bc_fid" labelOnTop="0"/>
    <field name="fid" labelOnTop="0"/>
    <field name="geom_type" labelOnTop="0"/>
    <field name="ident" labelOnTop="0"/>
    <field name="inoutfc" labelOnTop="0"/>
    <field name="name" labelOnTop="0"/>
    <field name="note" labelOnTop="0"/>
    <field name="time_series_fid" labelOnTop="0"/>
  </labelOnTop>
  <widgets/>
  <conditionalstyles>
    <rowstyles/>
    <fieldstyles/>
  </conditionalstyles>
  <expressionfields/>
  <previewExpression>fid</previewExpression>
  <mapTip></mapTip>
  <layerGeometryType>4</layerGeometryType>
</qgis>
