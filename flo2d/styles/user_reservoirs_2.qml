<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis labelsEnabled="0" hasScaleBasedVisibilityFlag="0" readOnly="0" maxScale="0" simplifyMaxScale="1" minScale="1e+8" simplifyDrawingHints="0" simplifyLocal="1" version="3.2.3-Bonn" simplifyAlgorithm="0" simplifyDrawingTol="1">
  <renderer-v2 symbollevels="0" forceraster="0" enableorderby="0" type="singleSymbol">
    <symbols>
      <symbol clip_to_extent="1" type="marker" alpha="1" name="0">
        <layer pass="0" locked="0" class="SimpleMarker" enabled="1">
          <prop k="angle" v="0"/>
          <prop k="color" v="18,22,249,255"/>
          <prop k="horizontal_anchor_point" v="1"/>
          <prop k="joinstyle" v="bevel"/>
          <prop k="name" v="triangle"/>
          <prop k="offset" v="0,0"/>
          <prop k="offset_map_unit_scale" v="3x:0,0,0,0,0,0"/>
          <prop k="offset_unit" v="MM"/>
          <prop k="outline_color" v="0,0,0,255"/>
          <prop k="outline_style" v="no"/>
          <prop k="outline_width" v="0"/>
          <prop k="outline_width_map_unit_scale" v="3x:0,0,0,0,0,0"/>
          <prop k="outline_width_unit" v="MM"/>
          <prop k="scale_method" v="diameter"/>
          <prop k="size" v="3"/>
          <prop k="size_map_unit_scale" v="3x:0,0,0,0,0,0"/>
          <prop k="size_unit" v="MM"/>
          <prop k="vertical_anchor_point" v="1"/>
          <data_defined_properties>
            <Option type="Map">
              <Option value="" type="QString" name="name"/>
              <Option name="properties"/>
              <Option value="collection" type="QString" name="type"/>
            </Option>
          </data_defined_properties>
        </layer>
      </symbol>
    </symbols>
    <rotation/>
    <sizescale/>
  </renderer-v2>
  <customproperties>
    <property value="&quot;fid&quot;" key="dualview/previewExpressions"/>
    <property value="0" key="embeddedWidgets/count"/>
    <property key="variableNames"/>
    <property key="variableValues"/>
  </customproperties>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
  <layerOpacity>1</layerOpacity>
  <SingleCategoryDiagramRenderer attributeLegend="1" diagramType="Pie">
    <DiagramCategory scaleDependency="Area" minScaleDenominator="-2.14748e+9" diagramOrientation="Up" barWidth="5" labelPlacementMethod="XHeight" penWidth="0" lineSizeType="MM" penColor="#000000" maxScaleDenominator="1e+8" backgroundColor="#ffffff" sizeScale="3x:0,0,0,0,0,0" backgroundAlpha="255" height="15" scaleBasedVisibility="0" penAlpha="255" enabled="0" opacity="1" sizeType="MM" lineSizeScale="3x:0,0,0,0,0,0" width="15" minimumSize="0" rotationOffset="270">
      <fontProperties style="" description="MS Shell Dlg 2,8.25,-1,5,50,0,0,0,0,0"/>
      <attribute label="" field="" color="#000000"/>
    </DiagramCategory>
  </SingleCategoryDiagramRenderer>
  <DiagramLayerSettings zIndex="0" dist="0" showAll="1" priority="0" obstacle="0" placement="0" linePlacementFlags="2">
    <properties>
      <Option type="Map">
        <Option value="" type="QString" name="name"/>
        <Option type="Map" name="properties">
          <Option type="Map" name="show">
            <Option value="true" type="bool" name="active"/>
            <Option value="fid" type="QString" name="field"/>
            <Option value="2" type="int" name="type"/>
          </Option>
        </Option>
        <Option value="collection" type="QString" name="type"/>
      </Option>
    </properties>
  </DiagramLayerSettings>
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
    <field name="wsel">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field name="n_value">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field name="notes">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
  </fieldConfiguration>
  <aliases>
    <alias index="0" field="fid" name=""/>
    <alias index="1" field="name" name=""/>
    <alias index="2" field="wsel" name=""/>
    <alias index="3" field="n_value" name=""/>
    <alias index="4" field="notes" name=""/>
  </aliases>
  <excludeAttributesWMS/>
  <excludeAttributesWFS/>
  <defaults>
    <default expression="" applyOnUpdate="0" field="fid"/>
    <default expression="" applyOnUpdate="0" field="name"/>
    <default expression="" applyOnUpdate="0" field="wsel"/>
    <default expression="" applyOnUpdate="0" field="n_value"/>
    <default expression="" applyOnUpdate="0" field="notes"/>
  </defaults>
  <constraints>
    <constraint constraints="3" unique_strength="1" notnull_strength="1" field="fid" exp_strength="0"/>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="name" exp_strength="0"/>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="wsel" exp_strength="0"/>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="n_value" exp_strength="0"/>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="notes" exp_strength="0"/>
  </constraints>
  <constraintExpressions>
    <constraint exp="" field="fid" desc=""/>
    <constraint exp="" field="name" desc=""/>
    <constraint exp="" field="wsel" desc=""/>
    <constraint exp="" field="n_value" desc=""/>
    <constraint exp="" field="notes" desc=""/>
  </constraintExpressions>
  <attributeactions>
    <defaultAction value="{00000000-0000-0000-0000-000000000000}" key="Canvas"/>
  </attributeactions>
  <attributetableconfig sortExpression="" actionWidgetStyle="dropDown" sortOrder="0">
    <columns>
      <column type="field" width="-1" hidden="0" name="fid"/>
      <column type="actions" width="-1" hidden="1"/>
      <column type="field" width="-1" hidden="0" name="name"/>
      <column type="field" width="-1" hidden="0" name="wsel"/>
      <column type="field" width="-1" hidden="0" name="n_value"/>
      <column type="field" width="-1" hidden="0" name="notes"/>
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
from PyQt4.QtGui import QWidget

def my_form_open(dialog, layer, feature):
	geom = feature.geometry()
	control = dialog.findChild(QWidget, "MyLineEdit")
]]></editforminitcode>
  <featformsuppress>0</featformsuppress>
  <editorlayout>generatedlayout</editorlayout>
  <editable>
    <field editable="1" name="fid"/>
    <field editable="1" name="n_value"/>
    <field editable="1" name="name"/>
    <field editable="1" name="notes"/>
    <field editable="1" name="wsel"/>
  </editable>
  <labelOnTop>
    <field labelOnTop="0" name="fid"/>
    <field labelOnTop="0" name="n_value"/>
    <field labelOnTop="0" name="name"/>
    <field labelOnTop="0" name="notes"/>
    <field labelOnTop="0" name="wsel"/>
  </labelOnTop>
  <widgets/>
  <conditionalstyles>
    <rowstyles/>
    <fieldstyles/>
  </conditionalstyles>
  <expressionfields/>
  <previewExpression>fid</previewExpression>
  <mapTip>crestwidth</mapTip>
  <layerGeometryType>0</layerGeometryType>
</qgis>
