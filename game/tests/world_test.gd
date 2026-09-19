extends SceneTree
const World = preload("res://scripts/world.gd")
var failed := false

func check(value: bool, label: String) -> void:
	print(("PASS " if value else "FAIL ") + label)
	failed = failed or not value

func _init() -> void:
	call_deferred("run")

func run() -> void:
	var world := World.new()
	root.add_child(world)
	for i in range(90):
		await physics_frame
	check(world.player.is_on_floor(), "player lands on real collision floor")
	var start_y: float = world.player.position.y
	Input.action_press("jump")
	await physics_frame
	await physics_frame
	Input.action_release("jump")
	for i in range(12):
		await physics_frame
	check(world.player.position.y > start_y + 0.5, "input makes character jump")
	world.player.position.y = -30
	for i in range(3):
		await physics_frame
	check(world.falls == 1 and world.player.position.y > 0, "fall respawns at checkpoint")
	world._on_checkpoint(world.player, 3)
	check(world.checkpoint == 3, "checkpoint progression")
	world._on_checkpoint(world.player, 0)
	check(world.checkpoint == 3, "checkpoint never moves backward")
	world._on_checkpoint(world.player, 11)
	check(world.finished and world.player.locked, "finish freezes player")
	world.restart_run()
	check(not world.finished and world.checkpoint == 0 and world.falls == 0, "restart resets run")
	quit(1 if failed else 0)
