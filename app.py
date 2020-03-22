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

import os
import nuke
import nozonscripts
import tank
import sgtk
from tank import TankError


class NukeOCIONode(tank.platform.Application):

    def init_app(self):
        """
        Called as the application is being initialized
        """

        # this app should not do anything if nuke is run without gui.

        if nuke.env['gui']:

            # first deal with nuke root settings: we don't need a context for this

            self._setOCIOSettingsOnRootNode() # if I don't do this and do a File/New in Nuke, the new instance of nuke does not set the OCIO settings on the root node.
            self._add_root_callbacks()
            self.log_debug("Loading tk-nuke-ocio app.")

            #setting stuff as the app is initialised. Not very good if the context is changed ?

            if self.context.entity is not None:
                self.event = self.context.entity['name']
                self.sequence = ''
                try:
                    self.sequence = self.context.as_template_fields(self.sgtk.templates['nuke_shot_work'])['Sequence']
                except:
                    self.log_debug("No sequence found because no sequence key in the nuke_shot_work template")
                self.camera_colorspace = self._getCameraColorspaceFromShotgun()

                self._setOCIOSettingsOnRootNode()

                self._add_callbacks()

                self.log_debug("The camera colorspace for shot %s from sequence %s has been fetched from Shotgun and is '%s'" % (self.event, self.sequence, self.camera_colorspace))

        else:
            pass


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

    def _remove_root_callbacks(self):
        """
        Removed previously added callbacks
        """
        nuke.removeOnCreate(self._setOCIOSettingsOnRootNode, nodeClass='Root' )


    def _add_callbacks(self):
        """
        Add callbacks to watch for certain events:
        """

        nuke.addOnUserCreate(self._setOCIOColorspaceContext, nodeClass="OCIOColorSpace")
        nuke.addKnobChanged(self._setReadNodeOCIO, {'callType': 'knobChanged'}, nodeClass="Read")
        nuke.addOnCreate(self._setReadNodeOCIO, {'callType': 'onCreate'}, nodeClass="Read")
        nuke.addOnCreate(self._setOCIODisplayContext, nodeClass="OCIODisplay")

        nuke.addOnCreate(self._warningNoCameraColorspace, nodeClass='Root' )

    def _remove_callbacks(self):
        """
        Removed previously added callbacks
        """
        nuke.removeOnUserCreate(self._setOCIOColorspaceContext, nodeClass="OCIOColorSpace")
        nuke.removeKnobChanged(self._setReadNodeOCIO, {'callType': 'knobChanged'}, nodeClass="Read")
        nuke.removeOnCreate(self._setReadNodeOCIO, {'callType': 'onCreate'}, nodeClass="Read")
        nuke.removeOnCreate(self._setOCIODisplayContext, nodeClass="OCIODisplay")

        nuke.removeOnCreate(self._warningNoCameraColorspace, nodeClass='Root' )

    def _setOCIOColorspaceContext(self):
        '''
        Setting up the knobs of the OCIOColorspace node
        If the node is created as a child of a read node use the read node filepath to try to populate the event number,
        the camera colorspace and set the in colorspace to the colorspace defined in the string of the filepath
        If the node is created with no close connection to a read node we assume the node should be related to the current
        context, so we use the event number and the camera colorspace from Shotgun
        '''

        ocioNode = nuke.thisNode()

        # First we setup the node to the event number and camera colorspace from the current context
        
        ocioNode['key1'].setValue('EVENT')
        ocioNode['value1'].setValue(self.event)
        ocioNode['key2'].setValue('CAMERA')
        ocioNode['value2'].setValue(self.camera_colorspace)
        ocioNode['key3'].setValue('SEQUENCE')
        ocioNode['value3'].setValue(self.sequence)

        # Now let's try to detect a read node in the upstream nodes

        if not nuke.selectedNodes(): # no nodes selected, stop here
            return
        selNode = nuke.selectedNode()
        upstreamNodes = [] # we will store an arbitrary number of upstream nodes in this list
        upstreamNodes.append(selNode)

        for i in range(10):
            selNode = selNode.dependencies() # take the list of upstream dependent nodes, usually one but can be more if we have a node with multiple inputs
            if selNode: selNode = selNode[0] #we take only the first dependent upstream node, so we stay on the B side
            else: break # if there's nothing we have reached the end of the tree
            upstreamNodes.append(selNode)

        readNode = None
        for n in upstreamNodes:
            if n.Class() == 'Read':
                readNode = n
                break
        else : return # stop here if we have found no read node
        

        imagePath = readNode.knob('file').toScript()
        imagePath = nuke.filenameFilter(imagePath)
        
        tk = self.sgtk
        tmpl = tk.template_from_path(imagePath)


        colorspace = None

        if tmpl:
            fields = tmpl.get_fields(imagePath)
            shot = fields.get("Shot")
            if shot: # we know the shot code, so set it on the OCIO context tab
                ocioNode['key1'].setValue('EVENT')
                ocioNode['value1'].setValue(shot)

            colorspace = fields.get("colorspace")
            if not colorspace: # if there's no colorspace field in the template
                if tmpl.name == 'maya_render_output': colorspace = 'Flat'
                elif tmpl.name == 'hiero_render_Jpeg_path': colorspace = 'sRGB'
                elif tmpl.name == 'hiero_render_Flat_path': colorspace = 'Flat'
                elif tmpl.name == 'hiero_render_path': colorspace = 'Flat'
            if colorspace: # if we now have a colorspace, set it on the ocio context
                ocioNode['key2'].setValue('CAMERA')
                ocioNode['value2'].setValue(colorspace)

            sequence = fields.get('Sequence')
            if sequence: #we know the name of the sequence, set it on the OCIO context tab
                ocioNode['key3'].setValue('SEQUENCE')
                ocioNode['value3'].setValue(sequence)  


        if colorspace:
            ocioNode.knob('in_colorspace').setValue(colorspace)
            ocioNode.knob('value2').setValue(colorspace)
            ocioNode.knob('out_colorspace').setValue('Flat')


    def _setReadNodeOCIO(self, kwargs):

        # setting OCIO context info for Read Nodes
        # used in a KnobChanged callback (OnUserCreate callback does not work because file knob is not set when the OnUserCreate function is called)
        # possible problem when changing the file to the exact same file : in that case the colorspace will be reset
        
        # what should I do when creating a read from a sequence with a shotgrade or globalgrade baked in ? Interpret as sRGB ?
        # what If I load a render from another project ? Interpret as Flat anyway ?

        callType = kwargs['callType']
        readNode = nuke.thisNode()

        if callType == 'knobChanged':
            # print 'knobchanged callback'
            fileknob = nuke.thisKnob()
            if fileknob.name() != 'file': # stop if the knob being changed is not the file knob
                return
        if callType == 'onCreate': # if there's any info already in the ocio context, we don't want to change anything
            # print 'oncreate callback'
            if readNode['key1'].value()   != '': return
            if readNode['value1'].value() != '': return
            if readNode['key2'].value()   != '': return
            if readNode['value2'].value() != '': return

        imagePath = readNode.knob('file').toScript()
        imagePath = nuke.filenameFilter(imagePath)
        # print 'imagePath', imagePath
        tk = self.sgtk
        tmpl = tk.template_from_path(imagePath)
        self.log_debug("Template is %s" % tmpl)
        if tmpl:
            fields = tmpl.get_fields(imagePath)
            shot = fields.get("Shot")
            if shot: # we know the shot code, so set it on the OCIO context tab
                readNode['key1'].setValue('EVENT')
                readNode['value1'].setValue(shot)

            colorspace = fields.get("colorspace")
            if not colorspace: # if there's no colorspace field in the template
                if tmpl.name == 'maya_render_output': colorspace = 'Flat'
                elif tmpl.name == 'hiero_render_Jpeg_path': colorspace = 'sRGB'
                elif tmpl.name == 'hiero_render_Flat_path': colorspace = 'Flat'
                elif tmpl.name == 'hiero_render_path': colorspace = 'Flat'
            if colorspace: # if we now have a colorspace set it on the ocio context and on the read node colorspace knob
                readNode['key2'].setValue('CAMERA')
                readNode['value2'].setValue(colorspace)
                readNode['colorspace'].setValue(colorspace)

            sequence = fields.get('Sequence')
            if sequence: #we know the name of the sequence, set it on the OCIO context tab
                readNode['key3'].setValue('SEQUENCE')
                readNode['value3'].setValue(sequence)

    def _setOCIODisplayContext(self):

        OCIODisplayNode = nuke.thisNode()

        if OCIODisplayNode.knob('key1').value() != 'EVENT':
            OCIODisplayNode.knob('key1').setValue('EVENT')
        if OCIODisplayNode.knob('value1').value() != self.event:
           OCIODisplayNode.knob('value1').setValue(self.event)
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

        return data['sg_camera_colorspace']

    
    def _warningNoCameraColorspace(self):

        camera_colorspace =  self.camera_colorspace
        #camera_colorspace = self._getCameraColorspaceFromShotgun()

        if camera_colorspace == '' or camera_colorspace == None:
            nuke.message('Warning : The camera colorspace of shot %s could not be determined.\n\
                Please check the Shot infos on our shotgun website and fill the camera colorspace field (sRGB for pure CGI stuff)' % self.event)
        
        self.log_debug("Checking the camera colorspace in shotgun")


    def _setOCIOSettingsOnRootNode(self):

        ocio_template = self.get_template("ocio_template")
        ocio_path = self.sgtk.paths_from_template(ocio_template, {})[0]
        ocio_path = ocio_path.replace(os.path.sep, "/")

        workingSpace = self.get_setting('workingspace')

        nuke.root().knob("colorManagement").setValue("OCIO") 
        nuke.root().knob("OCIO_config").setValue("custom")
        if ocio_path != nuke.filenameFilter(nuke.root().knob("customOCIOConfigPath").value()): # only set the ocio path if it's not already set. Do not change it if it's the same path written for another platform
            nuke.root().knob("customOCIOConfigPath").setValue(ocio_path)
        nuke.root().knob("workingSpaceLUT").setValue(workingSpace)



