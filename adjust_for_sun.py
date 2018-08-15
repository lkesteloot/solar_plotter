# This script reads in a G-code file and moves the points around to adjust for the
# motion of the sun when burning something with the magnifying glass XY table.

# The program assumes that the board starts out perpendicular to the sun's light.

import sys, time, math

DEG_TO_RAD = math.pi / 180
DAY_TO_SEC = 24 * 60 * 60
INCH_TO_METER = 0.0254
IPM_TO_MPS = INCH_TO_METER/60.0

# Inches per minute for G0.
G0_METERS_PER_SECOND = 60 * IPM_TO_MPS

# http://en.wikipedia.org/wiki/Earth
EARTH_SUN_DIST_M = 149597887.5 * 1000

# http://wiki.answers.com/Q/What_is_the_earth%27s_inclination_exactly
EARTH_INCLINATION = 23.4 * DEG_TO_RAD

# San Francisco
LATITUDE = 37.775
LONGITUDE = -122.417

# Palo Alto
LATITUDE = 37.442
LONGITUDE = -122.141

# Santa Cruz
LATITUDE = 36.974
LONGITUDE = -122.029

LATITUDE *= DEG_TO_RAD
LONGITUDE *= DEG_TO_RAD

# http://en.wikipedia.org/wiki/Earth_radius
EARTH_RADIUS_M = 6371 * 1000

# Distance from magnifying glass to surface.
MAG_HEIGHT_M = 0.40

def get_seconds_since_midnight():
    now = time.localtime()
    sys.stderr.write("Now:" + str(now) + "\n")
    midnight = (now[0], now[1], now[2], 0, 0, 0, 0, 0, 0)
    sys.stderr.write("Midnight:" + str(midnight) + "\n")
    time_since_midnight_s = int(time.mktime(now) - time.mktime(midnight))
    if time_since_midnight_s < 0:
        time_since_midnight_s += DAY_TO_SEC

    return time_since_midnight_s

# Return a string of seconds, nicely formatted.
def printable_seconds(seconds):
    seconds = int(seconds)

    minutes = seconds / 60
    seconds -= minutes * 60

    hours = minutes / 60
    minutes -= hours * 60

    return "%02d:%02d:%02d" % (hours, minutes, seconds)

def printable_vector(v):
    v = ["%.4f" % value for value in v]

    return "(" + ", ".join(v) + ")"

# Amount above equator that the sun is this time of year.
def get_sun_inclination(max_inclination, day_of_year):
    # Winter Solstice is, like, the 22nd of December.
    WINTER_SOLSTICE = -9

    # Delta from that.
    days_from_solstice = day_of_year - WINTER_SOLSTICE

    # Normalize to radians.
    radians_from_solstice = days_from_solstice / 365.0 * 2 * math.pi

    # Negate because we calculate from winter Solstice, where it's
    # lowest.
    return -math.cos(radians_from_solstice) * max_inclination

# Converts a longtitude and latitude and radius to (x,y,z) point.
def polar_to_cartesian(radius, longitude, latitude):
    return (
            radius * math.cos(longitude) * math.cos(latitude),
            radius * math.sin(longitude) * math.cos(latitude),
            radius * math.sin(latitude)
    )

# Returns (a + b)
def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

# Returns (a - b)
def subtract(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def get_length(a):
    return math.sqrt(dot(a, a))

# Returns a unit vector for "a", or None if zero.
def normalize(a):
    length = get_length(a)
    if length == 0:
        return None
    return scalar_multiply(1.0/length, a)

def scalar_multiply(s, a):
    return tuple([e*s for e in a])

# http://en.wikipedia.org/wiki/Cross_product
def cross_product(b, c):
    return (
            b[1]*c[2] - b[2]*c[1],
            b[2]*c[0] - b[0]*c[2],
            b[0]*c[1] - b[1]*c[0]
            )

def dot(b, c):
    return b[0]*c[0] + b[1]*c[1] + b[2]*c[2]

# Given a line through p aligned with v, intersects with the plane through o
# perpendicular to z, then finds 2D coordinate given x and y. All 3D vectors must
# be normalized. Returns a 2D vector.
def project(p, v, o, x, y, z):
    # Find the point q at intersection of line and plane.  We have two
    # equations we must solve for simultaneously to find t (and hence q):
    #     q = p + vt            (point must be on line)
    #     dot(q - o, z) = 0     (point must be on plane)
    # Therefore:
    #     dot(p + vt - o, z) = 0
    #     dot(p + vt - o, z) = 0
    #     dot(p - o, z) + dot(vt, z) = 0
    #     dot(vt, z) = -dot(p - o, z)
    #     t*dot(v, z) = -dot(p - o, z)
    #     t = -dot(p - o, z)/dot(v, z)
    dot_vz = dot(v, z)
    if dot_vz == 0:
        # Vector and plane are parallel.
        return None

    # Find t.
    t = -dot(subtract(p, o), z) / dot_vz

    # Plug back into line equation to find the intersection point.
    q = add(p, scalar_multiply(t, v))

    # Project in the plane's space.
    dq = subtract(q, o)
    return (dot(dq, x), dot(dq, y))

# Get the sun's position given our longitude and the number of seconds since midnight.
def get_sun_pos(longitude, time_since_midnight_s):
    # Convert seconds to radians, where one day is 2*PI. Negate because as time goes
    # on, the sun moves towards negative radians.
    radians_since_midnight = -float(time_since_midnight_s) / DAY_TO_SEC * 2 * math.pi

    # Get the day of year to get the inclination.
    day_of_year = time.localtime()[7]

    # The inclination of the sun right now.
    sun_inclination = get_sun_inclination(EARTH_INCLINATION, day_of_year)
    # sys.stderr.write("sun_inclination: %f\n" % (sun_inclination / DEG_TO_RAD,))

    # Convert to a position. Add our longitude plus half a circle since it's
    # relative to midnight for us.
    sun_pos = polar_to_cartesian(EARTH_SUN_DIST_M,
            longitude + math.pi + radians_since_midnight, sun_inclination)

    return sun_pos

# Returns the position of the magnifying glass, of the origin of the board,
# and three unit vectors for the basis vectors of the board.
def get_initial_position(longitude, latitude, time_since_midnight_s):
    # Earth space: center is at (0,0,0), X axis is through 0 longitude, Y is 90 deg
    # longitude, and Z axis is north pole.
    mag_pos = polar_to_cartesian(EARTH_RADIUS_M, longitude, latitude)
    sys.stderr.write("mag_pos: %s\n" % (printable_vector(mag_pos),))

    # Get the position of the sun at this time, in earth space.
    sun_pos = get_sun_pos(longitude, time_since_midnight_s)
    sys.stderr.write("sun_pos: %s\n" % (printable_vector(sun_pos),))

    # Vector from the magnifying glass to the sun.
    mag_to_sun = normalize(subtract(sun_pos, mag_pos))

    # Assume that the board is facing the sun directly, and that its bottom
    # edge (the X axis) is on the ground. From this we can compute a set of
    # basis vectors for it. The Z axis will point at the sun. We already have
    # this in mag_to_sun. This can be crossed with the mag_pos vector to get
    # the X axis, and from there the Y axis.
    board_z = normalize(mag_to_sun)
    board_x = normalize(cross_product(mag_pos, board_z))
    board_y = normalize(cross_product(board_z, board_x))
    # sys.stderr.write("Board: %r %r %r\n" % (board_x, board_y, board_z))

    # The origin of the board.
    board = subtract(mag_pos, scalar_multiply(MAG_HEIGHT_M, mag_to_sun))

    return mag_pos, board, board_x, board_y, board_z

def get_offset(mag_pos, board, board_x, board_y, board_z, time_since_midnight_s):
    # Get the position of the sun at this time, in earth space.
    sun_pos = get_sun_pos(LONGITUDE, time_since_midnight_s)
    # sys.stderr.write("    sun_pos: %s\n" % (printable_vector(sun_pos),))

    # Vector from the magnifying glass to the sun.
    mag_to_sun = normalize(subtract(sun_pos, mag_pos))

    # Determine 2D position based on basis vectors
    offset = project(mag_pos, mag_to_sun, board, board_x, board_y, board_z)

    return offset

def offset_test(time_since_midnight_s):
    mag_pos, board, board_x, board_y, board_z = get_initial_position(LONGITUDE,
            LATITUDE, time_since_midnight_s)

    # See every minute for 20 minutes.
    for dt in range(0, 20*60, 60):
        new_time_s = time_since_midnight_s + dt
        print "Time:", printable_seconds(new_time_s)

        offset = get_offset(mag_pos, board, board_x, board_y, board_z, new_time_s)

        # print "Burn 3D:", burn_3d
        print "    Offset:", printable_vector(offset)

# Parses a G-code file from the file "inf" to the file "outf", modifying X and Y
# coordinates according to the movement of the sun.
def parse_g_code(time_since_midnight_s, inf, outf):
    # Get our initial position information.
    mag_pos, board, board_x, board_y, board_z = get_initial_position(LONGITUDE,
            LATITUDE, time_since_midnight_s)

    g = None    # Current G code.
    x = 0.0
    y = 0.0
    f = G0_METERS_PER_SECOND
    t = 0       # Original time.

    bounds = (999999, 999999, -999999, -999999)
    last_offset = None

    # Read the input one line at a time.
    for line in inf.xreadlines():
        new_line = ""
        state = None
        vs = ""
        suppress = False
        specified_x = None
        specified_y = None
        specified_f = None

        for ch in line:
            uch = ch.upper()

            if state is None:
                if ch == "(":
                    state = "comment"
                elif uch == "G":
                    state = "parsing_g"
                    g = 0
                elif uch == "X":
                    state = "parsing_x"
                    vs = ""
                    suppress = True
                elif uch == "Y":
                    state = "parsing_y"
                    vs = ""
                    suppress = True
                elif uch == "F":
                    state = "parsing_f"
                    vs = ""
            elif state == "comment":
                if ch == ")":
                    state = None
            elif state == "parsing_g":
                if ch >= "0" and ch <= "9":
                    g = g*10 + int(ch)
                else:
                    state = None
            elif state == "parsing_x" or state == "parsing_y" or state == "parsing_f":
                if ch in "0123456789+-.":
                    vs = vs + ch
                else:
                    if state == "parsing_x":
                        specified_x = float(vs)*INCH_TO_METER
                    elif state == "parsing_y":
                        specified_y = float(vs)*INCH_TO_METER
                    elif state == "parsing_f":
                        f = float(vs)*IPM_TO_MPS
                        outf.write("(f is now %g, text was %s)\n" % (f, vs))
                    else:
                        assert False
                    suppress = False
                    state = None

            if not suppress:
                new_line += ch

        if specified_x is not None or specified_y is not None:
            # Coordinates are optional.
            if specified_x is None:
                new_x = x
            else:
                new_x = specified_x
            if specified_y is None:
                new_y = y
            else:
                new_y = specified_y

            # Calculate new point.
            new_time_s = time_since_midnight_s + t
            offset = get_offset(mag_pos, board, board_x, board_y, board_z, new_time_s)
            last_offset = offset

            # Offset our coordinates.
            new_x -= offset[0]
            new_y -= offset[1]

            # Calculate distance from (x,y,z) to (new_x,new_y,new_z).
            dist = get_length(subtract( (x,y,0), (new_x,new_y,0) ))

            # Calculate time at speed F after that distance.
            if g == 0:
                effective_f = G0_METERS_PER_SECOND
            else:
                effective_f = f
            op_time_s = dist / effective_f
            outf.write("(dist = %g, effective_f = %g, op_time = %g)\n" % (dist, effective_f, op_time_s))

            # Calculate delta point after that time.
            t += op_time_s

            # Expand bounds with the new location.
            if g == 1:
                bounds = (
                        min(bounds[0], x, new_x),
                        min(bounds[1], y, new_y),
                        max(bounds[2], x, new_x),
                        max(bounds[3], y, new_y)
                        )

            # Reconstruct line with new values.
            new_line = new_line.strip()
            if new_x is not None:
                new_line += " X%f" % (new_x / INCH_TO_METER,)
            if new_y is not None:
                new_line += " Y%f" % (new_y / INCH_TO_METER,)
            new_line += "\n"

            x = new_x
            y = new_y

        outf.write("(Time is " + printable_seconds(t) + ")\n")
        outf.write(new_line)

    outf.flush()
    sys.stderr.write("Total running time: " + printable_seconds(t) + "\n")
    sys.stderr.write("Bounds: " + printable_vector(scalar_multiply(1/INCH_TO_METER, bounds)) + "\n")
    sys.stderr.write("Last offset: " + printable_vector(scalar_multiply(1/INCH_TO_METER, last_offset)) + "\n")

def main():
    time_since_midnight_s = get_seconds_since_midnight()
    time_since_midnight_s = 14*60*60
    sys.stderr.write("time_since_midnight_s: %d %s\n" %
            (time_since_midnight_s, printable_seconds(time_since_midnight_s)))

    # offset_test(time_since_midnight_s)
    parse_g_code(time_since_midnight_s, sys.stdin, sys.stdout)

main()
