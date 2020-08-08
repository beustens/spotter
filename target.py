import json # to load diameters from json file


class Target:
    '''
    Ring sizes on the target relative to the mirror
    '''
    def __init__(self, data=None, targetNum=0):
        '''
        :param data: dictionary with
            "mirror": <mirror diameter>
            "rings": dictionary with "<ring number>": <ring diameter>
        :param targetNum: when given, loads the data from the database
        '''
        if data:
            self.makeRings(data)
        elif targetNum > 0:
            with open('targets.json') as database:
                data = json.load(database)
                self.makeRings(data)
        else:
            raise ValueError('Provide either data dictionary or target number')
    

    def makeRings(self, data):
        '''
        Generates the ring <-> size association
        '''
        d = float(data['mirror'])
        self.rings = {int(k): float(v)/d for k, v in data['rings'].items()}
    

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
        # calculations according to https://math.stackexchange.com/questions/76457/check-if-a-point-is-within-an-ellipse
        h, k = ringBounds.center # ellipse center coordinates
        x, y = point # point to test
        rx = ringBounds.width/2 # ellipse semi x-axis
        ry = ringBounds.height/2 # ellipse semi y-axis
        return (x-h)**2/rx**2+(y-k)**2/ry**2
    

    def isPointInRing(self, point, ringBounds):
        '''
        Checks if point is within ring

        :param point: (left, top) pixel coordinates
        :param ringBounds: Rect object of ring bounds
        :returns: True if point is in ring or False if not
        '''
        return True if self.pointInEllipse(point, ringBounds) <= 1. else False
    

    def pointInRing(self, point, mirrorBounds):
        '''
        Get ring closest to center for point

        :param point: (left, top) pixel coordinates
        :returns: ring number
        '''
        rings = sorted(self.rings.keys(), reverse=True) # get rings in falling order
        for ring in rings:
            # get ring bounds
            size = self.rings[ring]
            ringBounds = mirrorBounds.scaled(size)
            # check if point is in bounds
            if self.isPointInRing(point, ringBounds):
                return ring
        
        return ring