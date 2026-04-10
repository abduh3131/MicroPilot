"""Minimal VehicleModel for virtual panda / comma body operation.

The full VehicleModel uses a bicycle model for steering geometry.
For the comma body robot, the relationship between curvature and
steering angle is simple: angle = curvature * steerRatio * wheelbase.
"""
import math


class VehicleModel:
  def __init__(self, CP):
    self.CP = CP
    self.steer_ratio = float(CP.steerRatio)
    self.wheelbase = float(CP.wheelbase)

  def get_steer_from_curvature(self, curvature, v_ego, roll=0.0):
    """Convert desired curvature to steering angle (degrees)."""
    # For a simple body robot: angle = atan(curvature * wheelbase) * steer_ratio
    # For small angles this simplifies to curvature * wheelbase * steer_ratio
    if abs(curvature) < 1e-6:
      return 0.0
    return math.degrees(math.atan(curvature * self.wheelbase)) * self.steer_ratio

  def calc_curvature(self, steer_angle_rad, v_ego, roll=0.0):
    """Convert steering angle (radians) to curvature."""
    # Inverse of get_steer_from_curvature
    effective_angle = steer_angle_rad / self.steer_ratio
    if abs(effective_angle) < 1e-6:
      return 0.0
    return math.tan(effective_angle) / self.wheelbase
