extends Node3D
const Rules = preload("res://scripts/rules.gd")
const Player = preload("res://scripts/player.gd")
var player: Player
var checkpoint := 0
var elapsed := 0.0
var falls := 0
var finished := false
var hud: Label
var telemetry_clock := 0.0

func _ready() -> void:
	_setup_inputs()
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -30, 0)
	sun.light_energy = 1.4
	sun.shadow_enabled = true
	add_child(sun)
	var environment := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("9fc6ce")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("c9deda")
	env.ambient_light_energy = 0.65
	environment.environment = env
	add_child(environment)
	for i in range(Rules.COUNT):
		_platform(i)
	player = Player.new()
	player.name = "Player"
	add_child(player)
	player.respawn(Vector3(0, 0.8, 0))
	_make_hud()

func _setup_inputs() -> void:
	var mapping := {"left":KEY_A, "right":KEY_D, "forward":KEY_W, "back":KEY_S, "jump":KEY_SPACE, "restart":KEY_R}
	for action in mapping:
		if not InputMap.has_action(action):
			InputMap.add_action(action)
			var event := InputEventKey.new()
			event.physical_keycode = mapping[action]
			InputMap.action_add_event(action, event)

func _platform(index: int) -> void:
	var body := StaticBody3D.new()
	body.name = "Platform%d" % index
	body.position = Rules.platform_position(index)
	var size := Vector3(Rules.WIDTH, 0.6, Rules.WIDTH)
	if index == 0:
		size = Vector3(8, 0.6, 8)
	var collider := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collider.shape = shape
	body.add_child(collider)
	var instance := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	instance.mesh = mesh
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("168f95") if Rules.is_checkpoint(index) else Color("e9e2c7")
	instance.material_override = material
	body.add_child(instance)
	add_child(body)
	if Rules.is_checkpoint(index):
		var marker := Area3D.new()
		marker.collision_layer = 0
		marker.collision_mask = 2
		var sensor := CollisionShape3D.new()
		var sensor_shape := BoxShape3D.new()
		sensor_shape.size = Vector3(size.x - 0.3, 1.7, size.z - 0.3)
		sensor.shape = sensor_shape
		sensor.position.y = 1.15
		marker.add_child(sensor)
		body.add_child(marker)
		marker.body_entered.connect(_on_checkpoint.bind(index))

func _on_checkpoint(body: Node3D, index: int) -> void:
	if body != player:
		return
	checkpoint = maxi(checkpoint, index)
	if index == Rules.COUNT - 1:
		finished = true
		player.locked = true

func _make_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	hud = Label.new()
	hud.position = Vector2(24, 20)
	hud.add_theme_color_override("font_color", Color("142d36"))
	hud.add_theme_font_size_override("font_size", 24)
	layer.add_child(hud)
	var help := Label.new()
	help.text = "RIDGE RUNNER  |  WASD move  /  SPACE jump  /  RMB look  /  R restart\nReach the teal checkpoints. Touch: arrows + JUMP; drag right side to look."
	help.position = Vector2(24, 62)
	help.add_theme_color_override("font_color", Color("142d36"))
	layer.add_child(help)
	var restart := Button.new()
	restart.text = "RESTART"
	restart.position = Vector2(1080, 22)
	restart.size = Vector2(150, 50)
	restart.pressed.connect(restart_run)
	layer.add_child(restart)
	for item in [["left","<",Vector2(40,570)], ["right",">",Vector2(220,570)], ["forward","^",Vector2(130,480)], ["back","v",Vector2(130,660)], ["jump","JUMP",Vector2(1120,600)]]:
		var button := TouchScreenButton.new()
		button.action = item[0]
		button.position = item[2]
		var rect := RectangleShape2D.new()
		rect.size = Vector2(84, 70)
		button.shape = rect
		button.visibility_mode = TouchScreenButton.VISIBILITY_TOUCHSCREEN_ONLY
		var panel := Polygon2D.new()
		panel.polygon = PackedVector2Array([Vector2(-42,-35),Vector2(42,-35),Vector2(42,35),Vector2(-42,35)])
		panel.color = Color(0.08,0.18,0.21,0.65)
		button.add_child(panel)
		var label := Label.new()
		label.text = item[1]
		label.position = Vector2(-30,-16)
		label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		button.add_child(label)
		layer.add_child(button)

func restart_run() -> void:
	checkpoint = 0
	elapsed = 0
	falls = 0
	finished = false
	player.respawn(Vector3(0, 0.8, 0))

func _physics_process(delta: float) -> void:
	if Input.is_action_just_pressed("restart"):
		restart_run()
	if not finished:
		elapsed += delta
		if player.position.y < Rules.platform_position(checkpoint).y - 8.0:
			falls += 1
			player.respawn(Rules.platform_position(checkpoint) + Vector3(0, 0.8, 0))
	hud.text = "%s  |  %.1fs  |  checkpoint %d  |  falls %d" % ["FINISH!" if finished else "CLIMB",elapsed,checkpoint,falls]
	telemetry_clock += delta
	if OS.has_feature("web") and telemetry_clock >= 0.1:
		telemetry_clock = 0.0
		var state := {"frames":Engine.get_physics_frames(), "x":player.position.x, "y":player.position.y, "z":player.position.z, "floor":player.is_on_floor(), "checkpoint":checkpoint, "falls":falls, "finished":finished}
		JavaScriptBridge.eval("window.__RIDGE=" + JSON.stringify(state), true)
