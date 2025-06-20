# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
OCIO handling for Nuke

"""
from __future__ import print_function
import os
import nuke
import sgtk
import PyOpenColorIO as OCIO


class NukeOCIONode(sgtk.platform.Application):

    def init_app(self):
        """
        Called as the application is being initialized
        """

        # first deal with nuke root settings: we don't need a context for this
        self._setOCIOSettingsOnRootNode() # if I don't do this and do a File/New in Nuke, the new instance of nuke does not set the OCIO settings on the root node.
        self._add_root_callbacks()
        self.log_debug("Loading tk-nuke-ocio app.")

        fw = self.frameworks['tk-framework-nozon']
        self.csp = fw.import_module("colorspace")

        if self.context.entity:
            self.exec_app(self.context)

        self.config_colorspaces = self.csp.ColorSpace().get_config_colorspaces()


    def exec_app(self, context):


        self.entity_name = context.entity['name']
        self.sequence = ''
        try:
            self.sequence = context.as_template_fields(self.sgtk.templates['nuke_shot_work'])['Sequence']
        except:
            self.log_debug("No sequence found because no sequence key in the nuke_shot_work template")
        
        self.camera_colorspace, self.shot_lut = self._getColorspaceInfoFromShotgun(context)


        self._add_callbacks()

        self.log_debug("Shot %s from sequence %s : The camera colorspace is: %s and the shot lut is: %s " % (self.entity_name, 
                                                                            self.sequence, self.camera_colorspace, self.shot_lut))




    @property
    def context_change_allowed(self):
        """
        Specifies that context changes are allowed.

        """
        return False


    def destroy_app(self):
        """
        Called when the app is unloaded/destroyed
        """
        self.log_debug("Destroying tk-nuke-ocio app")
        
        # remove any callbacks that were registered by the handler:
        self._remove_root_callbacks()
        self._remove_callbacks()        

    def _add_root_callbacks(self):
        """
        Add callbacks to watch for certain events:
        """
        nuke.addOnCreate(self._setOCIOSettingsOnRootNode, nodeClass='Root' )
        nuke.addDefaultColorspaceMapper(self._nozonDefaultColorspaceMapper)

    def _remove_root_callbacks(self):
        """
        Removed previously added callbacks
        """
        nuke.removeOnCreate(self._setOCIOSettingsOnRootNode, nodeClass='Root' )
        nuke.removeDefaultColorspaceMapper(self._nozonDefaultColorspaceMapper)


    def _add_callbacks(self):
        """
        Add callbacks to watch for certain events:
        """
        nuke.addOnUserCreate(self._setOCIOContext, nodeClass="OCIOColorSpace")
        nuke.addOnCreate(self._setOCIOContext, nodeClass="Read")
        nuke.addOnCreate(self._setOCIODisplayContext, nodeClass="OCIODisplay")
        nuke.addOnCreate(self._warningNoCameraColorspace, nodeClass='Root' )

    def _remove_callbacks(self):
        """
        Removed previously added callbacks
        """
        nuke.removeOnUserCreate(self._setOCIOContext, nodeClass="OCIOColorSpace")
        nuke.removeOnCreate(self._setOCIOContext, nodeClass="Read")
        nuke.removeOnCreate(self._setOCIODisplayContext, nodeClass="OCIODisplay")
        nuke.removeOnCreate(self._warningNoCameraColorspace, nodeClass='Root' )


    def _setOCIOContext(self):
        '''
        Setting the color context on OCIO context

        The context variables on OCIO nodes (eg OCIO Colorspace node, Read node) is used whenever the colorspace 
        depends on a context to be properly resolved. (e.g. Shotgrade)

        This will always use the context of the current shot, even for Read nodes from other comps

        When importing an offline plate from another shot, assuming this offline plate has that shot's baked in shotgrade,
        interpreting it with the Shotgrade of the current shot will be cancelled to the viewer Shotgrade lut of the current
        shot, thus the external read node will be seen with its actual baked in shotgrade

        NB: when copy pasting a read node from one comp to the other, the ocio context will change

        '''


        node = nuke.thisNode()


        # self.log_debug("setting ocio context on %s" % node.name())

        node['key1'].setValue('EVENT')
        node['value1'].setValue(self.entity_name)
        node['key2'].setValue('CAMERA')
        node['value2'].setValue(self.camera_colorspace)
        node['key3'].setValue('SEQUENCE')
        node['value3'].setValue(self.sequence)
        node['key4'].setValue('SHOTLUT')
        node['value4'].setValue(self.shot_lut)








    def _setOCIODisplayContext(self):

        OCIODisplayNode = nuke.thisNode()

        if OCIODisplayNode.knob('key1').value() != 'EVENT':
            OCIODisplayNode.knob('key1').setValue('EVENT')
        if OCIODisplayNode.knob('value1').value() != self.entity_name:
           OCIODisplayNode.knob('value1').setValue(self.entity_name)
        if OCIODisplayNode.knob('key2').value() != 'CAMERA':
            OCIODisplayNode.knob('key2').setValue('CAMERA')
        if OCIODisplayNode.knob('value2').value() != self.camera_colorspace:
            OCIODisplayNode.knob('value2').setValue(self.camera_colorspace)
        if OCIODisplayNode.knob('key3').value() != 'SEQUENCE':
            OCIODisplayNode.knob('key3').setValue('SEQUENCE')
        if OCIODisplayNode.knob('value3').value() != self.sequence:
           OCIODisplayNode.knob('value3').setValue(self.sequence)
        if OCIODisplayNode.knob('key4').value() != 'SHOTLUT':
            OCIODisplayNode.knob('key4').setValue('SHOTLUT')
        if OCIODisplayNode.knob('value4').value() != self.shot_lut:
           OCIODisplayNode.knob('value4').setValue(self.shot_lut)



    def _getColorspaceInfoFromShotgun(self, context):

        entity = context.entity

        sg_entity_type = entity["type"]  # should be Shot
        sg_filters = [["id", "is", entity["id"]]]  #  code of the current shot
        sg_fields = ['sg_camera_colorspace', 'sg_shot_lut']

        data = self.shotgun.find_one(sg_entity_type, filters=sg_filters, fields=sg_fields)

        if not data:
            return ("", "")

        camera_colorspace = data.get('sg_camera_colorspace')
        shot_lut = data.get('sg_shot_lut')

        self.log_debug("Getting info from Shotgun : camera colorspace is: %s and shot lut is: %s" % (camera_colorspace, shot_lut))

        return (str(camera_colorspace or ''), str(shot_lut or ''))


    
    def _warningNoCameraColorspace(self):

        camera_colorspace =  self.camera_colorspace

        if camera_colorspace == '' or camera_colorspace == None:
            nuke.message('Warning : The camera colorspace of shot %s could not be determined.\n\
                Please check the Shot infos on our shotgun website and fill the camera colorspace field' % self.entity_name)

        
        self.log_debug("Checking the camera colorspace in shotgun")



    def _setOCIOSettingsOnRootNode(self):

        ocio_template = self.get_template("ocio_template")
        ocio_path = self.sgtk.paths_from_template(ocio_template, {})[0]
        ocio_path = ocio_path.replace(os.path.sep, "/")

        nuke.root().knob("colorManagement").setValue("OCIO") 
        nuke.root().knob("OCIO_config").setValue("custom")
        if ocio_path != nuke.filenameFilter(nuke.root().knob("customOCIOConfigPath").value()): # only set the ocio path if it's not already set. Do not change it if it's the same path written for another platform
            nuke.root().knob("customOCIOConfigPath").setValue(ocio_path)
        
        working_space = self.get_setting("working_space")
        nuke.root().knob("workingSpaceLUT").setValue(working_space)

        # Force reload the color config
        # nuke.root().knob("reloadConfig").execute()


    def _nozonDefaultColorspaceMapper(self, colorspaceName, dataTypeHint, *args, **kwargs):
        """
        Useful to override default color spaces derived from metadata, file type,...
        see https://learn.foundry.com/nuke/developers/13.0/pythonreference/callbacks.html
        """
        # print("colorspace name is: %s " % colorspaceName)
        # print("dataTypeHint is: %s " % dataTypeHint)

        read_node = nuke.thisNode()

        # I notice that in NukeStudio this gets called from the root node, i.e.
        # nuke.thisNode() is the root node. So we need to check if this is a Read node
        if not read_node.Class() == "Read":
            return colorspaceName

        filepath = read_node.knob('file').getValue()
        filepath = nuke.filenameFilter(filepath)
        filepath = os.path.normpath(filepath)
        filename = os.path.basename(filepath)
        file_ext = os.path.splitext(filename)[1]

        for cs in self.config_colorspaces:
            if cs in filename:
                colorspaceName = cs

        # Draft mp4 files have the original colorspace name in their filename, which in that case should be ignored.
        if file_ext == ".mp4":
            colorspaceName = "sRGB"

        if colorspaceName == "rec709" and dataTypeHint == -1: # works for mp4 files
            colorspaceName = "sRGB"

        # The following was not working : setting Nuke to default MXF files to be interpreted as Alexa :
        # This is working until a transcode process opens a nuke process > the nuke export process doesn't inherit
        # this defaultcolorspacematter, which makes it fall back again to 'Gamma2.2'
        # if colorspaceName == "Gamma2.2" and dataTypeHint == -1: # works for mxf files
        #     colorspaceName = "AlexaV3LogC"

        return colorspaceName