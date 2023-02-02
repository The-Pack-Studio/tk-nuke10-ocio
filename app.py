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


class NukeOCIONode(sgtk.platform.Application):

    def init_app(self):
        """
        Called as the application is being initialized
        """

        # first deal with nuke root settings: we don't need a context for this
        self._setOCIOSettingsOnRootNode() # if I don't do this and do a File/New in Nuke, the new instance of nuke does not set the OCIO settings on the root node.
        self._add_root_callbacks()
        self.log_debug("Loading tk-nuke-ocio app.")

        #setting stuff as the app is initialised. Not very good if the context is changed ?
        if self.context.entity is not None:
            self.entity_name = self.context.entity['name']
            self.sequence = ''
            try:
                self.sequence = self.context.as_template_fields(self.sgtk.templates['nuke_shot_work'])['Sequence']
            except:
                self.log_debug("No sequence found because no sequence key in the nuke_shot_work template")
            self.camera_colorspace = self._getCameraColorspaceFromShotgun()

            # self._setOCIOSettingsOnRootNode()

            self._add_callbacks()

            self.log_debug("The camera(grading) colorspace for shot %s from sequence %s is '%s'" % (self.entity_name, self.sequence, self.camera_colorspace))


    @property
    def context_change_allowed(self):
        """
        Specifies that context changes are allowed.

        Donat note to self: I return False here, meaning that when the context changes
        > This app will be destroyed and reloaded
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
        nuke.addOnUserCreate(self._setOCIOColorspaceContext, nodeClass="OCIOColorSpace")
        nuke.addOnCreate(self._setOCIODisplayContext, nodeClass="OCIODisplay")
        nuke.addOnCreate(self._warningNoCameraColorspace, nodeClass='Root' )

    def _remove_callbacks(self):
        """
        Removed previously added callbacks
        """
        nuke.removeOnUserCreate(self._setOCIOColorspaceContext, nodeClass="OCIOColorSpace")
        nuke.removeOnCreate(self._setOCIODisplayContext, nodeClass="OCIODisplay")
        nuke.removeOnCreate(self._warningNoCameraColorspace, nodeClass='Root' )


    def _setOCIOColorspaceContext(self):
        '''
        Setting up the knobs of the OCIOColorspace node based on current context
        In previous versions of this app, I checked if a read node from another shot was attached to the OCIO Colorspace node, and checked that
        read node to find it's shot
        '''

        ocioNode = nuke.thisNode()

        ocioNode['key1'].setValue('EVENT')
        ocioNode['value1'].setValue(self.entity_name)
        ocioNode['key2'].setValue('CAMERA')
        ocioNode['value2'].setValue(self.camera_colorspace)
        ocioNode['key3'].setValue('SEQUENCE')
        ocioNode['value3'].setValue(self.sequence)


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


    def _getCameraColorspaceFromShotgun(self):

        entity = self.context.entity

        sg_entity_type = entity["type"]  # should be Shot
        sg_filters = [["id", "is", entity["id"]]]  #  code of the current shot
        sg_fields = ['sg_camera_colorspace']

        data = self.shotgun.find_one(sg_entity_type, filters=sg_filters, fields=sg_fields)

        if not data:
            return None

        return data.get('sg_camera_colorspace')

    
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
        # By convention, the scene_linear role is used as working space
        nuke.root().knob("workingSpaceLUT").setValue("scene_linear")


    def _nozonDefaultColorspaceMapper(self, colorspaceName, dataTypeHint, *args, **kwargs):
        """
        Useful to override default color spaces derived from metadata, file type,...
        see https://learn.foundry.com/nuke/developers/13.0/pythonreference/callbacks.html
        """
        # print("colorspace name is: %s " % colorspaceName)
        # print("dataTypeHint is: %s " % dataTypeHint)

        node = nuke.thisNode()
        cs_knob = node.knob('colorspace')
        filepath = node.knob('file').getValue()
        filename = os.path.basename(filepath)

        file_ext = os.path.splitext(filepath)[1]

        allColorspaces = nuke.colorspaces.getColorspaceList(cs_knob)[1:]
        if cs_knob.getFlag(nuke.STRIP_CASCADE_PREFIX):
            allColorspaces = [cs.split("\t")[-1] for cs in allColorspaces]

        # search for colorspace as a substring in the filename
        for cs in allColorspaces:
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