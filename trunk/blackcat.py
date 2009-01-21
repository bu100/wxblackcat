import wx
import os
import sys
import string
import copy

try:
    import psyco
    psyco.full()
except ImportError:
    pass

try:
    from wx import glcanvas
    haveGLCanvas = True
except ImportError:
    haveGLCanvas = False

try:
    from OpenGL.GL import *
    from OpenGL.GLUT import *
    haveOpenGL = True
except ImportError:
    haveOpenGL = False

import logging
import pprint
import math

class EndFileException(Exception):
    def __init__(self, args=None):
        self.args = args

class FormatError(Exception):
    def __init__(self, args=None):
        self.args = args

class Point:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0

    def __str__(self):
        s = '(%f, %f, %f) ' % (self.x, self.y, self.z)
        return s

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y and self.z == other.z

class Line:
    
    def __init__(self):
        self.p1 = Point()
        self.p2 = Point()

    def __eq__(self, other):
        ret = (self.p1 == other.p1 and self.p2 == other.p2) or (self.p1 == other.p2 and self.p2 == other.p1)
        return ret

def intersect(x1, y1, x2, y2, x):
    ''' compute y'''
    y = (y2 - y1) / (x2 - x1) * (x - x1) + y1
    return y

def isIntersect(p1, p2, z):
    if (p1.z - z) * (p2.z - z) < 0.0:
        return True
    else:
        return False

def getIntersect(p1, p2, z):
    x1 = p1.x
    y1 = p1.y
    z1 = p1.z

    x2 = p2.x
    y2 = p2.y
    z2 = p2.z
    
    x = intersect(z1, x1, z2, x2, z)
    y = intersect(z1, y1, z2, y2, z)
    p = Point()
    p.x = x
    p.y = y
    p.z = z
    return p

class Facet:
    def __init__(self):
        self.normal = Point()
        self.points = (Point(), Point(), Point())

    def __str__(self):
        s = 'normal: ' + str(self.normal)
        s += ' points:'
        for p in self.points:
            s += str(p)
        return s
    
    def intersect(self, z):
        L1 = [True for p in self.points if p.z > z]
        L2 = [True for p in self.points if p.z < z]
        if len(L1) == 3 or len(L2) == 3:
            return None
        
        L1 = []
        L2 = []
        for i in range(3):
            p = self.points[i]
            if p.z == z:
                L1.append(i)
            else:
                L2.append(i)
        
        line = Line()
        points = self.points
        n = len(L1)
        if n == 0:
            line = self.intersect_0_vertex(points, z)
        elif n == 1:
            line = self.intersect_1_vertex(points[L1[0]], points[L2[0]], points[L2[1]], z)
        elif n == 2:
            i1 = L1[0]
            i2 = L1[1]
            line.p1 = points[i1]
            line.p2 = points[i2]
        else:
            line = None
        return line

    def intersect_0_vertex(self, points, z):
        L = []
        for i in range(3):
            next = (i + 1) % 3
            p1 = points[i]
            p2 = points[next]
            if isIntersect(p1, p2, z):
                p = getIntersect(p1, p2, z)
                L.append(p)
        
        assert len(L) == 2
        line = Line()
        line.p1 = L[0]
        line.p2 = L[1]
        return line

    def intersect_1_vertex(self, p1, p2, p3, z):
        p = getIntersect(p2, p3, z)
        line = Line()
        line.p1 = p1
        line.p2 = p
        return line

class Layer:

    def __init__(self):
        self.lines = []

    def empty(self):
        return len(self.lines) == 0

    def calcDimension(self):
        xlist = []
        ylist = []
        zlist = []
        for line in self.lines:
            p1 = line.p1
            p2 = line.p2
            
            xlist.append(p1.x)
            xlist.append(p2.x)
            ylist.append(p1.y)
            ylist.append(p2.y)
            zlist.append(p1.z)
            zlist.append(p2.z)
        
        self.minx = min(xlist)
        self.maxx = max(xlist)
        self.miny = min(ylist)
        self.maxy = max(ylist)
        self.minz = min(zlist)
        self.maxz = max(zlist)

        self.xsize = self.maxx - self.minx
        self.ysize = self.maxy - self.miny
        self.zsize = self.maxz - self.minz
        
class CadModel:
    def __init__(self):
        self.initLogger()
        self.loaded = False
        self.currLayer = -1

    def initLogger(self):
        #self.logger = logging.getLogger(self.__class__.__name__)
        self.logger = logging.getLogger("cadmodel")
        self.logger.setLevel(logging.DEBUG)
        h = logging.StreamHandler()
        h.setLevel(logging.DEBUG)
        f = logging.Formatter("%(levelname)s %(filename)s:%(lineno)d %(message)s")
        h.setFormatter(f)
        self.logger.addHandler(h)
    
    def getLine(self, f):
        line = f.readline()
        if not line:
            raise EndFileException, 'end of file'
        return line.strip()

    def getNormal(self, f):
        line = self.getLine(f)
        items = line.split()
        no = len(items)
        if no != 5:
            if no == 2 and items[0] == "endsolid":
                self.loaded = True
                raise EndFileException, 'endfile'
            else:
                raise FormatError, line
        
        if items[0] != 'facet' and items[1] != 'normal':
            raise FormatError, line

        L = map(lambda x: float(x), items[2:])
        normal = Point()
        normal.x = L[0]
        normal.y = L[1]
        normal.z = L[1]
        return normal

    def getOuterloop(self, f):
        line = self.getLine(f)
        if line != "outer loop":
            raise FormatError, line

    def getVertex(self, f):
        points = []
        for i in range(3):
            line = self.getLine(f)
            items = line.split()
            no = len(items)
            if no != 4:
                raise FormatError, line
            if items[0] != 'vertex':
                raise FormatError, line

            L = map(lambda x: float(x), items[1:])
            point = Point()
            point.x = L[0]
            point.y = L[1]
            point.z = L[2]
            points.append(point)
        return points
    
    def getEndloop(self, f):
        line = self.getLine(f) 
        if line != 'endloop':
            raise FormatError, line
    
    def getEndFacet(self, f):
        line = self.getLine(f)
        if line != 'endfacet':
            raise FormatError, line

    def getFacet(self, f):
        normal = self.getNormal(f)   
        self.getOuterloop(f)
        points = self.getVertex(f)
        facet = Facet()
        facet.normal = normal
        facet.points = points
        self.getEndloop(f)
        self.getEndFacet(f)
        return facet
    
    def getSolidLine(self, f):
        ''' Read the first line'''
        line = self.getLine(f)
        items = line.split()
        no = len(items)
        if no == 2 and items[0] == 'solid':
            self.modelName = items[1]
        else:
            raise FormatError, line
    
    def getDimension(self):
        if self.loaded:
            xlist = []
            ylist = []
            zlist = []
            for facet in self.facets:
                for p in facet.points:
                    xlist.append(p.x)
                    ylist.append(p.y)
                    zlist.append(p.z)
            self.minx = min(xlist)
            self.maxx = max(xlist)
            self.miny = min(ylist)
            self.maxy = max(ylist)
            self.minz = min(zlist)
            self.maxz = max(zlist)
            
            self.xsize = self.maxx - self.minx
            self.ysize = self.maxy - self.miny
            self.zsize = self.maxz - self.minz

            self.logger.debug(self.minx)
            self.logger.debug(self.maxx)
            self.logger.debug(self.miny)
            self.logger.debug(self.maxy)
            self.logger.debug(self.minz)
            self.logger.debug(self.maxz)

    def open(self, filename):
        try:
            f = open(filename) 
        except IOError, e:
            print e
            return False
        
        try:
            self.getSolidLine(f)
            self.facets = [] 
            while True:
                facet = self.getFacet(f)
                self.facets.append(facet)
        except EndFileException, e:
            pass
        except FormatError, e:
            print e.args
            return False
        
        if self.loaded:
            self.getDimension()
            self.logger.debug("no of facets:" + str(len(self.facets)))
            self.oldfacets = copy.deepcopy(self.facets)
            return True
        else:
            return False

    def slice(self, para):
        self.height = float(para["height"])
        self.pitch = float(para["pitch"])
        self.speed = float(para["speed"])
        self.fast = float(para["fast"])
        self.direction = para["direction"]
        self.scale = float(para["scale"])
        print para
        
        self.currLayer = -1
        self.scaleModel(self.scale)
        self.getDimension()
        self.createLayers()
        self.currLayer = 0
    
    def scaleModel(self, factor):
        self.facets = []
        for facet in self.oldfacets:
            nfacet = copy.deepcopy(facet)
            ps = []
            for p in nfacet.points:
                p.x *= factor
                p.y *= factor
                p.z *= factor
                ps.append(p)
            nfacet.points = ps
            self.facets.append(nfacet)
    
    def createLayers(self):
        self.layers = []
        z = self.minz + self.height
        while z < self.maxz:
            layer = self.createOneLayer(z)
            z += self.height
            if not layer.empty():
                self.layers.append(layer)
        print 'no of layers:', len(self.layers)                
    
    def existLine(self, lineList, line):
        for it in lineList:
            if line == it:
                print 'exist line'
                return True
        return False

    def createOneLayer(self, z):
        layer = Layer()
        lines = []
        for facet in self.facets:
            line = facet.intersect(z) 
            if line and not self.existLine(lines, line): 
                lines.append(line)
        layer.z = z
        layer.lines = lines
        return layer


class PathCanvas(glcanvas.GLCanvas):

    def __init__(self, parent):
        glcanvas.GLCanvas.__init__(self, parent, -1)

        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)

    def OnEraseBackground(self, event):
        pass

    def OnSize(self, event):
        if self.GetContext():
            self.SetCurrent()
            size = self.GetClientSize()
            glViewport(0, 0, size.width, size.height)
        self.Refresh(False)
        event.Skip()

    def OnPaint(self, event):
        dc = wx.PaintDC(self)
        self.SetCurrent()
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.SwapBuffers()

    def setLayers(self, layers):
        self.layers = layers
            
class ModelCanvas(glcanvas.GLCanvas):

    def __init__(self, parent):
        glcanvas.GLCanvas.__init__(self, parent, -1)
        self.init = False
        # initial mouse position
        self.lastx = self.x = 30
        self.lasty = self.y = 30
        self.size = None
        self.xangle = 0
        self.yangle = 0

        self.minx = -1
        self.maxx = 1
        self.miny = -1
        self.maxy = 1
        self.minz = 0
        self.maxz = 1

        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnMouseDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnMouseUp)
        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.loaded = False

        self.modelList = 1000
        self.getMaxLen()

    def getMaxLen(self):
        xlen = self.maxx - self.minx
        ylen = self.maxy - self.miny
        zlen = self.maxz - self.minz
        maxlen = math.sqrt(math.pow(xlen, 2) + math.pow(ylen, 2) + math.pow(zlen, 2))
        self.maxlen = maxlen
        return maxlen

    def getModelCenter(self):
        x = (self.minx + self.maxx) / 2
        y = (self.miny + self.maxy) / 2
        z = (self.minz + self.maxz) / 2
        return [x, y, z]

    def OnEraseBackground(self, event):
        pass # Do nothing, to avoid flashing on MSW.

    def OnPaint(self, event):
        dc = wx.PaintDC(self)
        self.SetCurrent()
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.showModel()
        self.SwapBuffers()

    def showModel(self):
        if not self.loaded:
            return
        
        #self.setupViewport()
        self.setupProjection()
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
         
        x, y, z = self.getModelCenter()
        glTranslatef(0, 0, -self.maxlen)
        # Rotate model
        glRotatef(self.xangle, 1, 0, 0)
        glRotatef(self.yangle, 0, 1, 1)
        
        # Move model to origin
        glTranslatef(-x, -y, -z)
        
        glCallList(self.modelList)

    def OnMouseDown(self, evt):
        self.CaptureMouse()
        self.x, self.y = self.lastx, self.lasty = evt.GetPosition()

    def OnMouseUp(self, evt):
        if self.HasCapture():
            self.ReleaseMouse()

    def OnMouseMotion(self, evt):
        if evt.Dragging() and evt.LeftIsDown():
            self.lastx, self.lasty = self.x, self.y
            self.x, self.y = evt.GetPosition()

            self.xangle += (self.y - self.lasty)
            self.yangle += (self.x - self.lastx)
            self.Refresh(False)

    def setModel(self, cadmodel):
        self.cadmodel = cadmodel
        
        self.minx = self.cadmodel.minx
        self.maxx = self.cadmodel.maxx
        self.miny = self.cadmodel.miny
        self.maxy = self.cadmodel.maxy
        self.minz = self.cadmodel.minz
        self.maxz = self.cadmodel.maxz 
        self.loaded = True
        self.initGL()
        self.getMaxLen()

    def OnSize(self, event):
        if self.GetContext():
            self.SetCurrent()
            self.setupViewport()
        self.Refresh(False)
        event.Skip()
    
    def setupViewport(self):
        size = self.GetClientSize()
        glViewport(0, 0, size.width, size.height)

    def setupProjection(self):
        maxlen = self.maxlen
        size = self.GetClientSize()
        w = size.width
        h = size.height
        
        half = maxlen / 2
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()

        if w <= h:
            factor = float(h) / w
            left = -half
            right = half
            bottom = -half * factor
            top = half * factor
        else:
            factor = float(w) / h
            left  = -half * factor 
            right = half * factor
            bottom = -half
            top = half
        near = 0
        far = maxlen * 2
        glOrtho(left, right, bottom, top, near, far)    

    def initGL(self):
        self.xangle = 0
        self.yangle = 0
        self.SetCurrent()
        self.setupGLContext()
        #self.setupViewport()
        #self.setupProjection()
        self.createModelList()
        self.Refresh()
    
    def setupGLContext2(self):
        self.SetCurrent()
        glMaterial(GL_FRONT, GL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
        glMaterial(GL_FRONT, GL_DIFFUSE, [0.8, 0.8, 0.8, 1.0])
        glMaterial(GL_FRONT, GL_SPECULAR, [1.0, 0.0, 1.0, 1.0])
        glMaterial(GL_FRONT, GL_SHININESS, 50.0)
        glLight(GL_LIGHT0, GL_AMBIENT, [0.0, 1.0, 0.0, 1.0])
        glLight(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        glLight(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glLight(GL_LIGHT0, GL_POSITION, [1.0, 1.0, 1.0, 0.0])
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glDepthFunc(GL_LESS)
        glEnable(GL_DEPTH_TEST)
        glClearColor(0.0, 0.0, 0.0, 1.0)
    
    def setupGLContext(self):
        glEnable(GL_LIGHTING);
        glEnable(GL_LIGHT0);

        ambientLight = [ 0.2, 0.2, 0.2, 1.0 ]
        diffuseLight = [ 0.8, 0.8, 0.8, 1.0 ]
        specularLight = [ 0.5, 0.5, 0.5, 1.0 ]
        position = [ -1.5, 1.0, -4.0, 1.0 ]

        glLightfv(GL_LIGHT0, GL_AMBIENT, ambientLight);
        glLightfv(GL_LIGHT0, GL_DIFFUSE, diffuseLight);
        glLightfv(GL_LIGHT0, GL_SPECULAR, specularLight);
        glLightfv(GL_LIGHT0, GL_POSITION, position);

        mcolor = [ 0.0, 0.0, 1.0, 1.0]
        glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, mcolor)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glPolygonMode(GL_BACK, GL_LINE)
        glColorMaterial(GL_FRONT, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_COLOR_MATERIAL)
        glMaterial(GL_FRONT, GL_SHININESS, 96)

    def setupGLContext_1(self):
        self.SetCurrent()
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        #glShadeModel(GL_FLAT)
        glShadeModel(GL_SMOOTH)
        glPolygonMode(GL_BACK, GL_LINE)
        
        maxlen = self.getMaxLen()

        # light0
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.4, 0.4, 0.9, 1.0])
        #glLight(GL_LIGHT0, GL_AMBIENT, [0.4, 0.4, 0.4, 1.0])
        glLight(GL_LIGHT0, GL_AMBIENT, [1.0, 1.0, 1.0, 1.0])
        glLight(GL_LIGHT0, GL_DIFFUSE, [0.7, 0.7, 0.7, 1.0])
        glLight(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glLight(GL_LIGHT0, GL_POSITION, [-50.0, 200.0, 200.0, 1.0])
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)

        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT, GL_AMBIENT_AND_DIFFUSE)

        glMaterial(GL_FRONT, GL_SPECULAR, [0.2, 0.2, 0.2, 1.0])
        #glMaterial(GL_FRONT, GL_SHININESS, 64)
        glClearColor(0.0, 0.0, 0.0, 1.0)

    def createModelList(self):
        glNewList(self.modelList, GL_COMPILE)
        if self.loaded:
            glColor(1, 0, 0)
            glBegin(GL_TRIANGLES)
            for facet in self.cadmodel.facets:
                normal = facet.normal
                glNormal3f(normal.x, normal.y, normal.z)
                for point in facet.points:
                    glVertex3f(point.x, point.y, point.z)
            glEnd()
        glEndList()

class ControlPanel(wx.Panel):
    
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        #self.SetBackgroundColour('gray')
        self.createControls()

    def createControls(self):
        mainsizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(self, -1, "Information")
        sizer.Add(lbl)
        sizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND)
        #box.Add(wx.Button(self, -1, "hi"))
        mainsizer.Add(sizer, 0, wx.ALL, 10)
        self.SetSizer(mainsizer)
        s = self.makeDimensionBox()
        sizer.Add(s)
    
    def makeDimensionBox(self):
        box = wx.StaticBox(self, -1, "Dimension")
        boxsizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        flex = wx.FlexGridSizer(rows=3, cols=2, hgap=2, vgap=2)
        self.sizetxt = []
        for label in ("Height", "Width", "Length"):
            lbl = wx.StaticText(self, -1, label=label)
            txt = wx.TextCtrl(self, -1, size=(90,-1), style=wx.TE_READONLY)
            self.sizetxt.append(txt)
            flex.Add(lbl)
            flex.Add(txt)
        boxsizer.Add(flex)
        return boxsizer

    def setDimension(self, x, y, z):
        self.sizetxt[0].SetValue(str(x))
        self.sizetxt[1].SetValue(str(y))
        self.sizetxt[2].SetValue(str(z))
        

class BlackCatFrame(wx.Frame):

    def __init__(self):
        wx.Frame.__init__(self, None, -1, "Black Cat", size=(640,480))
        self.createMenuBar()
        self.cadmodel = CadModel()
        self.statusbar = self.CreateStatusBar()
        self.createPanel()
        self.Centre()

    def createPanel(self):
        self.leftPanel  = ControlPanel(self)
        
        self.sp = wx.SplitterWindow(self)
        self.modelPanel = wx.Panel(self.sp, style=wx.SUNKEN_BORDER)
        self.pathPanel = wx.Panel(self.sp, style=wx.SUNKEN_BORDER)
        self.pathPanel.SetBackgroundColour('sky blue')
        
        # Model canvas
        self.modelCanvas = ModelCanvas(self.modelPanel)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.modelCanvas, 1, wx.EXPAND)
        self.modelPanel.SetSizer(sizer)

        box = wx.BoxSizer(wx.HORIZONTAL)
        box.Add(self.leftPanel, 0, wx.EXPAND)
        box.Add(self.sp, 1, wx.EXPAND)
        self.SetSizer(box)

        # Path canvas
        self.pathCanvas = PathCanvas(self.pathPanel)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.pathCanvas, 1, wx.EXPAND)
        self.pathPanel.SetSizer(sizer)

        self.sp.Initialize(self.modelPanel)
        self.sp.SplitVertically(self.modelPanel, self.pathPanel, 300)
        self.sp.SetMinimumPaneSize(10)

    def createMenuBar(self):
        menubar = wx.MenuBar()
        for data in self.menuData():
            label = data[0]
            items = data[1:]
            menubar.Append(self.createMenu(items), label)
        self.SetMenuBar(menubar)    

    def menuData(self):
        return (("&File", ("&Open", "Open CAD file", self.OnOpen),
                         ("&Slice", "Slice CAD model", self.OnSlice),
                         ("", "", ""),
                         ("&Quit", "Quit", self.OnQuit)),
                ("&Help", ("&About", "About this program", self.OnAbout))
                 )
    
    def OnAbout(self, event):
        info = wx.AboutDialogInfo()
        info.Name = "Black Cat"
        info.Version = "0.1"
        info.Copyright = "(C) 2009"
        info.Description = "Slice CAD model"
        info.Developers = ["Zhigang Liu"]
        wx.AboutBox(info)

    def createMenu(self, menuData):
        menu = wx.Menu()
        for label, status, handler in menuData:
            if not label:
                menu.AppendSeparator()
                continue
            menuItem = menu.Append(-1, label, status)
            self.Bind(wx.EVT_MENU, handler, menuItem)
        return menu

    def OnOpen(self, event):
        wildcard = "CAD std files (*.stl)|*.stl|All files (*.*)|*.*"
        dlg = wx.FileDialog(None, "Open CAD stl file", os.getcwd(), "", wildcard, wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.statusbar.SetStatusText(path)
            ok = self.cadmodel.open(path)
            if ok:
                self.modelCanvas.setModel(self.cadmodel)

                self.leftPanel.setDimension(self.cadmodel.xsize, self.cadmodel.ysize, self.cadmodel.zsize)
        dlg.Destroy()

    def OnSlice(self, event):
        dlg = ParaDialog(self)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            data =  dlg.getValues()
            self.cadmodel.slice(data)
            self.modelCanvas.setModel(self.cadmodel)
            self.leftPanel.setDimension(self.cadmodel.xsize, self.cadmodel.ysize, self.cadmodel.zsize)
            self.pathCanvas.setLayers(self.cadmodel.layers)
        else:
            print 'Cancel'
        dlg.Destroy()

    def OnQuit(self, event):
        pass

class CharValidator(wx.PyValidator):

    def __init__(self, data, key):
        wx.PyValidator.__init__(self)
        self.Bind(wx.EVT_CHAR, self.OnChar)
        self.data = data
        self.key = key

    def Clone(self):
        return CharValidator(self.data, self.key)
    
    def Validate(self, win):
        textCtrl = self.GetWindow()
        text = textCtrl.GetValue()
        if len(text) == 0:
            wx.MessageBox("This field must contain some text!", "Error")
            textCtrl.SetBackgroundColour('pink')
            textCtrl.Focus()
            textCtrl.Refresh()
            return False
        else:
            textCtrl.SetBackgroundColour(wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW))
            textCtrl.Refresh()
            return True
    
    def TransferToWindow(self):
        return True

    def TransferFromWindow(self):
        textCtrl = self.GetWindow()
        self.data[self.key] = textCtrl.GetValue()
        return True
    
    def OnChar(self, event):
        key = chr(event.GetKeyCode())
        if key in string.letters:
            return
        event.Skip()

class ParaDialog(wx.Dialog):

    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, -1, "Slice parameters", size=(200, 200))
        self.createControls()

    def createControls(self):
        labels = [("Layer height", "0.43", "height"), ("Pitch", "0.38", "pitch"), \
                  ("Scanning speed", "20", "speed"), ("Fast speed", "20", "fast")]
        
        self.data = {}
        outsizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        outsizer.Add(sizer, 0, wx.ALL, 10)
        box = wx.FlexGridSizer(rows=3, cols=2, hgap=5, vgap=5)
        for label, dvalue, key in labels:
            lbl = wx.StaticText(self, label=label)
            box.Add(lbl, 0, 0)
            txt = wx.TextCtrl(self, -1, dvalue, size=(80, -1), validator=CharValidator(self.data, key))
            box.Add(txt, 0, 0)
        sizer.Add(box, 0, 0)
        
        # slice direction
        lbl = wx.StaticText(self, label="Slice direction")
        box.Add(lbl, 0, 0)

        self.dirList = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
        self.dirChoice = dirChoice = wx.Choice(self, -1, (160, -1), choices=self.dirList)
        dirChoice.SetSelection(4)
        box.Add(dirChoice, 0, wx.EXPAND)
        
        # scale
        lbl = wx.StaticText(self, label="Scale factor")
        box.Add(lbl, 0, 0)
        scaleTxt = wx.TextCtrl(self, -1, "1", size=(80, -1), validator=CharValidator(self.data, "scale"))
        box.Add(scaleTxt, 0, wx.EXPAND)
        
        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND|wx.TOP|wx.BOTTOM, 5)
        
        #
        btnSizer = wx.BoxSizer(wx.HORIZONTAL)
        btnSizer.Add((10, 10), 1)
        okBtn = wx.Button(self, wx.ID_OK)
        okBtn.SetDefault()
        cancelBtn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        btnSizer.Add(okBtn)
        btnSizer.Add((10,10), 1)
        btnSizer.Add(cancelBtn)
        btnSizer.Add((10,10), 1)
        sizer.Add(btnSizer, 0, wx.EXPAND|wx.ALL, 10)

        self.SetSizer(outsizer)
        self.Fit()
    
    def getValues(self):
        self.data["direction"] = self.dirList[self.dirChoice.GetCurrentSelection()]
        return self.data

if __name__ == '__main__':
    app = wx.PySimpleApp()
    BlackCatFrame().Show()
    app.MainLoop()