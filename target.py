class Target:
    '''
    Ring sizes on the target relative to the mirror
    '''
    def __init__(self):
        self.makeRings()
    

    def makeRings(self):
        '''
        Generates the ring <-> size association

        This should be overidden for different target types
        '''
        self.rings = {
            1: 2.5, 
            2: 2.25, 
            3: 2., 
            4: 1.75, 
            5: 1.5, 
            6: 1.25, 
            7: 1., 
            8: 0.75, 
            9: 0.5,
            10: 0.25, 
            11: 0.125
        }
    

    def getRingBounds(self, mirrorBounds):
        '''
        Calculates bounds for each ring based on mirror

        :param mirrorBounds: Rect object of mirror
        :returns: list of Rect objects for each ring bounds
        '''
        return [mirrorBounds.scaled(ring) for ring in self.rings.values()]
    

    def pointInRing(self, point, ringBounds):
        '''
        Checks if point is within ring

        :param point: (left, top) pixel coordinates
        :param ringBounds: Rect object of ring bounds
        '''
        # calculations according to https://math.stackexchange.com/questions/76457/check-if-a-point-is-within-an-ellipse
        h, k = ringBounds.center # ellipse center coordinates
        x, y = point # point to test
        rx = ringBounds.width/2 # ellipse semi x-axis
        ry = ringBounds.height/2 # ellipse semi y-axis
        inside = ((x-h)**2/rx**2+(y-k)**2/ry**2) <= 1.
        return inside