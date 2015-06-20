#
# Robot PAU to motor mapping
# Copyright (C) 2014, 2015 Hanson Robotics
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301  USA

import math

class MapperBase:
  """
  Abstract base class for motor mappings.  Subclasses of MapperBase will
  be used to remap input values in received messages and convert them to
  motor units. Typically (but not always) the motor units are angles,
  measured in radians.

  The methods 'map' and '__init__' must be implemented when writing a
  new subclass.
  """

  def map(self, val):
    raise NotImplementedError

  def __init__(self, args, motor_entry):
    """
    On construction, mapper classes are passed an 'args' object and a
    'motor_entry' object, taken from a yaml file.  The args object will
    correspond to a 'function' property in the 'binding' stanza. The
    'motor_entry' will be the parent of 'binding', and is used mainly
    to reach 'min' and 'max' properties.  Thus, for example:

        foomotor:
           binding:
             function:
                - name: barmapper
                  bararg: 3.14
                  barmore:  2.718
           min: -1.0
           max: 1.0

    Thus, 'args' could be 'bararg', 'barmore', while 'motor_entry' would be
    the entire 'foomotor' stanza.
    """
    pass

# --------------------------------------------------------------

class Composite(MapperBase):
  """
  Composition mapper. This is initialized with an ordered list of
  mappers.  The output value is obtained by applying each of the
  mappers in sequence, one after the other.  The yaml file must
  specify a list of mappings in the function property.  For example:

          function:
            - name: quaternion2euler
              axis: z
            - name: linear
              scale: -2.92
              translate: 0

  would cause the quaternion2euler mapper function to be applied first,
  followed by the linear mapper.
  """
  def map(self, val):
    for mapper_instance in self.mapper_list:
      val = mapper_instance.map(val)
    return val

  def __init__(self, mapper_list):
    self.mapper_list = mapper_list

# --------------------------------------------------------------

class Linear(MapperBase):
  """
  Linear mapper.  This handles yaml entries that appear in one of the
  two forms.  One form uses inhomogenous coordinates, such as:

     function:
       - name: linear
         scale: -2.92
         translate: 0.3

  The other form specifies a min and max range, such as:

      function:
        - name: linear
          min: 0.252
          max: -0.342

  The first form just rescales the value to the indicated slope and
  offset. The second form rescales such that the indicated input min
  and max match the motor min and max.  For instance, in the second
  case, the input could be specified as min and max radians (for an
  angle), which is converted to motor min and max displacement.
  """

  def map(self, val):
    return (val + self.pretranslate) * self.scale + self.posttranslate

  def __init__(self, args, motor_entry):
    if args.has_key('scale') and args.has_key('translate'):
      self.pretranslate = 0
      self.scale = args['scale']
      self.posttranslate = args['translate']

    elif args.has_key('min') and args.has_key('max'):
      # Map the given 'min' and 'max' to the motor's 'min' and 'max'
      self.pretranslate = -args['min']
      self.scale = (motor_entry['max']-motor_entry['min'])/(args['max']-args['min'])
      self.posttranslate = motor_entry['min']

# --------------------------------------------------------------

class WeightedSum(MapperBase):
  """
  This will map min-max range for every term to intermediate min-max range
  (imin-imax) and then sum them up. Then the intermediate 0..1 range will be
  mapped to the motor min-max range.

  Example:

          function:
            - name: weightedsum
              imin: 0.402
              terms:
              - {min: 0, max: 1, imax: 0}
              - {min: 0, max: 0.6, imax: 1}
  """

  @staticmethod
  def _saturated(val, interval):
    return min(max(val, min(interval["min"],interval["max"])), max(interval["min"],interval["max"]))

  def map(self, vals):
    return sum(
      map(
        lambda (val, translate, scale, term):
          (self._saturated(val, term) + translate) * scale,
        zip(vals, self.pretranslations, self.scalefactors, self.termargs)
      )
    ) + self.posttranslate

  def __init__(self, args, motor_entry):
    range_motors = motor_entry["max"] - motor_entry["min"]

    self.posttranslate = args["imin"] * range_motors + motor_entry["min"]
    self.pretranslations = map(
      lambda term: -term["min"],
      args["terms"]
    )
    self.scalefactors = map(
      lambda term:
        (term["imax"]-args["imin"])/(term["max"]-term["min"])*range_motors,
      args["terms"]
    )
    self.termargs = args["terms"]

# --------------------------------------------------------------

class Quaternion2EulerYZX(MapperBase):
# class Quaternion2EulerYZY(MapperBase):

  def __init__(self, args, motor_entry):

    # These functions convert a quaternion to intrinsic Y-Z-X (or extrinsic
    # X-Z-Y) rotations in that order. So if X axis is the line of sight, Y -
    # vertical and Z - horizontal axes, Y, Z and X rotations will represent
    # Yaw, Pitch and Roll respectively. For a different rotation order, swap
    # q.x, q.y, q.z variables and 'x', 'y', 'z' keys.
    #
    # Properly speaking, these are not Euler angles, but Tate-Bryan angles.
    #
    # Note: Kudos to anyone who manages to put this swapping mechanism into code,
    # which also builds functions to compute only one of the rotations like
    # below. (it's harder than it looks)
    funcsByAxis = {
      'y': lambda q:
          math.atan2(
            -2 * (q.z * q.x - q.w * q.y),
            q.w**2 - q.y**2 - q.z**2 + q.x**2
          ),
      'z': lambda q:
          math.asin(
            2 * (q.y * q.x + q.w * q.z)
          ),
      'x': lambda q:
          math.atan2(
            -2 *(q.y * q.z - q.w * q.x),
            q.w**2 + q.y**2 - q.z**2 - q.x**2
          )
    }
    self.map = funcsByAxis[args['axis'].lower()]

class Quaternion2EulerYZY(MapperBase):
# class Quaternion2EulerYZX(MapperBase):

  def __init__(self, args, motor_entry):

    # These functions convert a quaternion to Y-Z-Y rotations.
    # The convention here is different than above, with X axis the line
    # of sight, Y axis to the left, and Z upwards.
    #  For a different rotation order, swap
    # q.x, q.y, q.z variables and 'x', 'y', 'z' keys.
    #
    def why(q) :
        # print("duuude q=", q)
        alpha = 2.0 * math.acos(q.w)
        # print("alpha = ", 180 *  alpha / 3.141592653)
        sina = math.sin(0.5 * alpha)
        cx = q.x / sina
        cy = q.y / sina
        cz = q.z / sina
        bx = 180 * math.acos(cx) / 3.141592653
        by = 180 * math.acos(cy) / 3.141592653
        bz = 180 * math.acos(cz) / 3.141592653
        # print("beta = ", bx, by, bz)
 
        tx = math.atan2(
            -2 *(q.y * q.z - q.w * q.x),
            q.w**2 + q.y**2 - q.z**2 - q.x**2
          )
        ty = math.atan2(
            -2 * (q.z * q.x - q.w * q.y),
            q.w**2 - q.y**2 - q.z**2 + q.x**2
          )
        tz = math.asin(
            2 * (q.y * q.x + q.w * q.z)
          )
        tx = 180 * tx / 3.14159
        ty = 180 * ty / 3.14159
        tz = 180 * tz / 3.14159
        print("duude pry=", tx, ty, tz)
        return math.atan2(
          -2 * (q.z * q.x - q.w * q.y),
          q.w**2 - q.y**2 - q.z**2 + q.x**2
        )
        
    funcsByAxis = {
      'x': lambda q: why(q),
      'z': lambda q:
          math.asin(
            2 * (q.y * q.x + q.w * q.z)
          ),
      'y': lambda q:
          math.atan2(
            -2 *(q.y * q.z - q.w * q.x),
            q.w**2 + q.y**2 - q.z**2 - q.x**2
          )
    }
    self.map = funcsByAxis[args['axis'].lower()]

# --------------------------------------------------------------

_mapper_classes = {
  "linear": Linear,
  "weightedsum": WeightedSum,
  "quaternion2euler": Quaternion2EulerYZX,
  "quaternion2YZY": Quaternion2EulerYZY
}

def build(yamlobj, motor_entry):
  if isinstance(yamlobj, dict):
    return _mapper_classes[yamlobj["name"]](yamlobj, motor_entry)

  elif isinstance(yamlobj, list):
    return Composite(
      [build(func_entry, motor_entry) for func_entry in yamlobj]
    )
