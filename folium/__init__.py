class Map:
    def __init__(self, location=None, zoom_start=10):
        self.location = location
        self.zoom_start = zoom_start
        self.elements = []
    def save(self, filename):
        with open(filename, 'w') as f:
            f.write('<html><body>Map placeholder</body></html>')
class Marker:
    def __init__(self, location=None, popup=None):
        self.location = location
        self.popup = popup
    def add_to(self, m):
        m.elements.append(('marker', self.location))
class PolyLine:
    def __init__(self, locations=None, color='blue'):
        self.locations = locations
        self.color = color
    def add_to(self, m):
        m.elements.append(('polyline', self.locations))
