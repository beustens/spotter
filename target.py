import json # to load diameters from json file


class Target:
    '''
    Ring sizes on the target relative to the mirror
    '''
    def __init__(self, data=None, name='', dbPath='html/targets.json', holeDia=0.):
        '''
        :param data: dictionary with
            "mirror": <mirror diameter>
            "rings": dictionary with "<ring number>": <ring diameter>
        :param name: when given, loads the data from the JSON database key
        :param dbPath: JSON database filepath
        :param holeDia: diameter of holes from munition in mm
        '''
        self.holeDia = holeDia
        self.name = ''
        self.dbPath = dbPath
        if data:
            self.makeRings(data)
        elif name:
            self.fromDatabase(name)
        else:
            raise ValueError('Provide either data dictionary or target number')
        
        self.mirrorBounds = None # mirror Rect in pixels
    

    def makeRings(self, data):
        '''
        Generates the ring <-> size association
        '''
        self.mirrorDia = float(data['mirror'])
        self.rings = {int(k): float(v)/self.mirrorDia for k, v in data['rings'].items()}
    

    def fromDatabase(self, name):
        '''
        Generates the rings from database key
        '''
        with open(self.dbPath) as f:
            database = json.load(f)
            data = database[name]
            self.makeRings(data)
            self.name = name
    

    def mmToPix(self, mm):
        '''
        Converts a size in mm to pixels
        '''
        return mm*self.mirrorBounds.width/self.mirrorDia
    

    @property
    def holeSize(self):
        '''
        :returns: hole size in pixels
        '''
        return self.mmToPix(self.holeDia)
    

    @property
    def ringBounds(self):
        '''
        :returns: list of Rect objects for each ring bounds in pixels
        '''
        return [self.mirrorBounds.scaled(size) for size in self.rings.values()]
    

    def pointInEllipse(self, point, ringBounds):
        '''
        Calculates how much a point is in a ellipse, defined by bounds

        :param point: (left, top) pixel coordinates
        :param ringBounds: Rect object of ring bounds
        :returns: relative value normalized to 1 = point on edge
        '''
        h, k = ringBounds.center # ellipse center coordinates
        x, y = point # point to test
        rx = ringBounds.width/2 # ellipse semi x-axis
        ry = ringBounds.height/2 # ellipse semi y-axis
        return (((x-h)/rx)**2+((y-k)/ry)**2)**0.5
    

    def isHoleInRing(self, point, ringBounds, hole=0):
        '''
        Checks if point is within ring

        :param point: (left, top) pixel coordinates
        :param ringBounds: Rect object of ring bounds in pixels
        :param hole: hole size in pixels
        :returns: True if point is in ring or False if not
        '''
        return True if self.pointInEllipse(point, ringBounds) <= 1+hole/ringBounds.width else False
    

    def pointInRing(self, pointPos, pointDia=0.):
        '''
        Get ring closest to center for point

        :param pointPos: (left, top) pixel coordinates
        :param pointDia: point diameter in mm
        :returns: ring number
        '''
        pointWidth = self.holeSize # hole size in pixels
        rings = sorted(self.rings.keys(), reverse=True) # get rings in falling order
        for ring in rings:
            # get ring bounds
            size = self.rings[ring]
            ringBounds = self.mirrorBounds.scaled(size)
            # check if point is in bounds
            if self.isHoleInRing(pointPos, ringBounds, pointWidth):
                return ring
        
        return ring