extends RefCounted
const SPEED := 6.0
const JUMP := 8.8
const GRAVITY := 24.0
const COYOTE := 0.12
const BUFFER := 0.12
const COUNT := 12
const STEP_Z := 5.0
const STEP_Y := 0.65
const WIDTH := 3.6

static func jump_height() -> float:
	return JUMP * JUMP / (2.0 * GRAVITY)

static func reach_at_height(height: float) -> float:
	var discriminant := JUMP * JUMP - 2.0 * GRAVITY * height
	if discriminant < 0.0:
		return -1.0
	return SPEED * (JUMP + sqrt(discriminant)) / GRAVITY

static func platform_position(index: int) -> Vector3:
	if index == 0:
		return Vector3.ZERO
	return Vector3(1.5 if index % 2 == 0 else -1.5, index * STEP_Y, -index * STEP_Z)

static func is_checkpoint(index: int) -> bool:
	return index % 3 == 0 or index == COUNT - 1
