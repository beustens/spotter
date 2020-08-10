import json # to load diameters from json file


class Target:
    '''
    Ring sizes on the target relative to the mirror
    '''
    def __init__(self, data=None, num=0):
        '''
        :param data: dictionary with
            "mirror": <mirror diameter>
            "rings": dictionary with "<ring number>": <ring diameter>
        :param num: when given, loads the data from the database
        '''
        if data:
            self.makeRings(data)
        elif num > 0:
            with open('targets.json') as f:
                database = json.load(f)
                data = database[str(num)]
                self.makeRings(data)
        else:
            raise ValueError('Provide either data dictionary or target number')
    

    def makeRings(self, data):
        '''
        Generates the ring <-> size association
        '''
        self.mirrorDia = float(data['mirror'])
        self.rings = {int(k): float(v)/self.mirrorDia for k, v in data['rings'].items()}
    

    def getRingBounds(self, mirrorBounds):
        '''
        Calculates bounds for each ring based on mirror

        :param mirrorBounds: Rect object of mirror
        :returns: list of Rect objects for each ring bounds
        '''
        return [mirrorBounds.scaled(size) for size in self.rings.values()]
    

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
    

    def pointInRing(self, point, mirrorBounds, pointDia=0.):
        '''
        Get ring closest to center for point

        :param point: (left, top) pixel coordinates
        :param mirrorBounds: Rect object of mirror bounds in pixels
        :param pointDia: point diameter in mm
        :returns: ring number
        '''
        pointWidth = pointDia*mirrorBounds.width/self.mirrorDia # hole size in pixels
        rings = sorted(self.rings.keys(), reverse=True) # get rings in falling order
        for ring in rings:
            # get ring bounds
            size = self.rings[ring]
            ringBounds = mirrorBounds.scaled(size)
            # check if point is in bounds
            if self.isHoleInRing(point, ringBounds, pointWidth):
                return ring
        
        return ring