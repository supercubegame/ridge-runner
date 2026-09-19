extends CharacterBody3D
const Rules = preload("res://scripts/rules.gd")
var yaw := 0.0
var pitch := -0.2
var coyote := 0.0
var buffered := 0.0
var locked := false
var pivot: Node3D
var look_finger := -1

func _ready() -> void:
	collision_layer = 2
	collision_mask = 1
	var collider := CollisionShape3D.new()
	var shape := CapsuleShape3D.new()
	shape.radius = 0.32
	shape.height = 1.6
	collider.shape = shape
	collider.position.y = 0.8
	add_child(collider)
	var visual := MeshInstance3D.new()
	var mesh := CapsuleMesh.new()
	mesh.radius = 0.32
	mesh.height = 1.6
	visual.mesh = mesh
	visual.position.y = 0.8
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("f6c343")
	visual.material_override = material
	add_child(visual)
	pivot = Node3D.new()
	pivot.position.y = 1.3
	add_child(pivot)
	var boom := SpringArm3D.new()
	boom.spring_length = 5.5
	boom.collision_mask = 1
	boom.margin = 0.2
	pivot.add_child(boom)
	var camera := Camera3D.new()
	camera.current = true
	camera.fov = 75
	boom.add_child(camera)
	floor_snap_length = 0.25

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if event.pressed else Input.MOUSE_MODE_VISIBLE
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= event.relative.x * 0.003
		pitch = clampf(pitch - event.relative.y * 0.003, -1.0, 0.35)
	if event is InputEventScreenTouch:
		if event.pressed and event.position.x > get_viewport().get_visible_rect().size.x * 0.5:
			look_finger = event.index
		elif not event.pressed and event.index == look_finger:
			look_finger = -1
	if event is InputEventScreenDrag and event.index == look_finger:
		yaw -= event.relative.x * 0.004
		pitch = clampf(pitch - event.relative.y * 0.004, -1.0, 0.35)

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		look_finger = -1
		for action in ["left", "right", "forward", "back", "jump"]:
			Input.action_release(action)

func _physics_process(delta: float) -> void:
	pivot.rotation = Vector3(pitch, yaw, 0)
	if locked:
		return
	coyote = Rules.COYOTE if is_on_floor() else maxf(0.0, coyote - delta)
	buffered = Rules.BUFFER if Input.is_action_just_pressed("jump") else maxf(0.0, buffered - delta)
	if not is_on_floor():
		velocity.y -= Rules.GRAVITY * delta
	if buffered > 0.0 and coyote > 0.0:
		velocity.y = Rules.JUMP
		coyote = 0.0
		buffered = 0.0
	var axis := Input.get_vector("left", "right", "forward", "back")
	var direction := Vector3(axis.x, 0, axis.y).rotated(Vector3.UP, yaw)
	velocity.x = direction.x * Rules.SPEED
	velocity.z = direction.z * Rules.SPEED
	move_and_slide()

func respawn(point: Vector3) -> void:
	global_position = point
	velocity = Vector3.ZERO
	coyote = 0.0
	buffered = 0.0
	locked = false
