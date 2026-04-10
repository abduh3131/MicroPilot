#!/usr/bin/env python3
"""fakes panda messages so openpilot daemons dont crash"""

import time
import cereal.messaging as messaging
from cereal import car, log
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.selfdrive.pandad.pandad_api_impl import can_list_to_can_capnp
from openpilot.common.swaglog import cloudlog


# builds the fake carparams for the body
def build_car_params():
  CP = car.CarParams.new_message()

  CP.brand = "body"
  CP.carFingerprint = "COMMA BODY"
  CP.notCar = True

  CP.openpilotLongitudinalControl = True
  CP.pcmCruise = False
  CP.transmissionType = "direct"

  CP.minEnableSpeed = 0.0
  CP.minSteerSpeed = 0.0
  CP.vEgoStopping = 0.02
  CP.vEgoStarting = 0.02

  CP.steerControlType = "torque"
  CP.steerActuatorDelay = 0.0
  CP.steerLimitTimer = 1.0
  CP.steerRatio = 0.5

  CP.wheelbase = 0.406
  CP.centerToFront = 0.203
  CP.mass = 9.0
  CP.tireStiffnessFactor = 1.0
  CP.wheelSpeedFactor = 1.0

  CP.tireStiffnessFront = 985.7
  CP.tireStiffnessRear = 1558.2
  CP.rotationalInertia = 0.348

  lt = CP.lateralTuning.init('torque')
  lt.friction = 0.0
  lt.latAccelFactor = 1.0
  lt.latAccelOffset = 0.0

  CP.longitudinalTuning.kpBP = [0.0]
  CP.longitudinalTuning.kpV = [0.5]
  CP.longitudinalTuning.kiBP = [0.0]
  CP.longitudinalTuning.kiV = [0.0]

  safety = CP.init('safetyConfigs', 1)
  safety[0].safetyModel = car.CarParams.SafetyModel.body
  safety[0].safetyParam = 0

  CP.dashcamOnly = False
  CP.passive = False
  CP.enableBsm = False

  return CP


# publishes fake panda and body messages at 100hz
def main():
  cloudlog.info("virtual_panda: starting")
  params = Params()

  CP = build_car_params()
  cp_bytes = CP.to_bytes()
  params.put("CarParams", cp_bytes)
  params.put_nonblocking("CarParamsCache", cp_bytes)
  params.put_nonblocking("CarParamsPersistent", cp_bytes)
  params.put_bool("FirmwareQueryDone", True)
  params.put_bool("ControlsReady", True)
  cloudlog.info("virtual_panda: CarParams written to params store")

  pm = messaging.PubMaster([
    'pandaStates',
    'peripheralState',
    'can',
    'carParams',
    'carState',
    'carOutput',
    'liveTracks',
  ])

  sm = messaging.SubMaster(['carControl', 'selfdriveState'])

  cp_msg = messaging.new_message('carParams', valid=True)
  cp_msg.carParams = CP
  pm.send('carParams', cp_msg)
  cloudlog.info("virtual_panda: initial carParams published")

  rk = Ratekeeper(100, print_delay_threshold=None)
  idx = 0
  start_time = time.monotonic()

  last_accel = 0.0
  last_torque = 0.0
  last_steer_angle = 0.0

  while True:
    sm.update(0)

    if idx % 10 == 0:
      dat = messaging.new_message('pandaStates', 1, valid=True)
      dat.pandaStates[0] = {
        'ignitionLine': True,
        'pandaType': 'tres',
        'controlsAllowed': True,
        'safetyModel': 'body',
        'safetyParam': 0,
        'faultStatus': 'none',
        'harnessStatus': 'normal',
      }
      pm.send('pandaStates', dat)

    if idx % 50 == 0:
      ps_msg = messaging.new_message('peripheralState', valid=True)
      ps_msg.peripheralState.pandaType = log.PandaState.PandaType.tres
      pm.send('peripheralState', ps_msg)

    pm.send('can', can_list_to_can_capnp([]))

    # rewrite carparams for the first 30 seconds so selfdrived picks them up
    elapsed = time.monotonic() - start_time
    if elapsed < 30.0 and idx % 100 == 0:
      params.put("CarParams", cp_bytes)
      params.put_bool("FirmwareQueryDone", True)
      params.put_bool("ControlsReady", True)

    if idx % 5000 == 0 and idx > 0:
      cp_msg = messaging.new_message('carParams', valid=True)
      cp_msg.carParams = CP
      pm.send('carParams', cp_msg)

    cs_msg = messaging.new_message('carState', valid=True)
    CS = cs_msg.carState
    CS.canValid = True
    CS.standstill = True
    CS.vEgo = 0.0
    CS.vEgoRaw = 0.0
    CS.aEgo = 0.0
    CS.yawRate = 0.0
    CS.steeringAngleDeg = last_steer_angle
    CS.steeringTorque = last_torque
    CS.steeringPressed = False
    CS.brakePressed = False
    CS.gasPressed = False
    CS.gearShifter = 'drive'
    CS.doorOpen = False
    CS.seatbeltUnlatched = False
    CS.cruiseState.available = True
    CS.cruiseState.enabled = True
    CS.cruiseState.speed = 10.0
    pm.send('carState', cs_msg)

    co_msg = messaging.new_message('carOutput', valid=True)
    if sm.updated['carControl']:
      act = sm['carControl'].actuators
      last_accel = float(act.accel)
      last_torque = float(act.torque)
      last_steer_angle = float(act.steeringAngleDeg)

    co_msg.carOutput.actuatorsOutput.accel = last_accel
    co_msg.carOutput.actuatorsOutput.torque = last_torque
    co_msg.carOutput.actuatorsOutput.steeringAngleDeg = last_steer_angle
    pm.send('carOutput', co_msg)

    lt_msg = messaging.new_message('liveTracks', valid=True)
    pm.send('liveTracks', lt_msg)

    idx += 1
    if idx % 500 == 0:
      engaged = sm['selfdriveState'].enabled if sm.valid['selfdriveState'] else False
      cloudlog.info(f"virtual_panda: frame={idx}, engaged={engaged}, accel={last_accel:.2f}, torque={last_torque:.2f}")

    rk.keep_time()


if __name__ == "__main__":
  main()
