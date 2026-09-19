extends SceneTree
const Rules = preload("res://scripts/rules.gd")
var failed := false

func check(value: bool, label: String) -> void:
	print(("PASS " if value else "FAIL ") + label)
	failed = failed or not value

func _init() -> void:
	check(is_equal_approx(Rules.jump_height(), 1.6133333333), "jump apex independent numeric oracle")
	check(Rules.reach_at_height(2.0) < 0, "unreachable elevation rejected")
	check(Rules.reach_at_height(Rules.STEP_Y) > 0, "platform height reachable")
	for i in range(1, Rules.COUNT):
		var delta := Rules.platform_position(i) - Rules.platform_position(i-1)
		var gap := Vector2(maxf(0,absf(delta.x)-Rules.WIDTH), maxf(0,absf(delta.z)-Rules.WIDTH)).length()
		check(gap + 0.64 < Rules.reach_at_height(delta.y), "edge gap + player diameter reachable: %d" % i)
	check(Rules.is_checkpoint(0) and Rules.is_checkpoint(3) and Rules.is_checkpoint(11), "checkpoint schedule")
	check(not Rules.is_checkpoint(2), "non-checkpoint negative fixture")
	quit(1 if failed else 0)
