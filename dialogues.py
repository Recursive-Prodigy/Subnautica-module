import random

BOOT = "Alterra telemetry link re-established. Your biological architecture remains surprisingly intact arec."
SHUTDOWN = "Telemetry link severed. PDA entering low-power standby. Do try to survive without corporate supervision."

# --- HYDRATION PROTOCOLS ---
HYDRATION_DUE_LINES = [
    "Fluid intake recommended. Your biological components are drying out.",
    "Reminder: Organic lifeforms require regular water replenishment. Alterra strongly recommends you seek fluid intake.",
    "Hydration levels falling below optimal threshold. Do find something non-toxic to drink.",
    "Hydration interval reached. While dehydration is technically an option, it is not economically viable."
]

HYDRATION_OVERDUE_LINES = [
    "Warning: Severe dehydration threshold approached. Seek fluid intake immediately.",
    "Vital signs suboptimal. Cellular desiccation in progress. I suggest you consume water before cognitive failure ensues.",
    "Emergency: Fluid reserves critical. At your current rate of water consumption, mummification will commence shortly.",
    "Corporate protocol mandates advising you to drink water. Ignoring this alert may void your biological warranty."
]

# --- NUTRITION PROTOCOLS ---
NUTRITION_DUE_LINES = [
    "Calorie intake recommended. Metabolic output is declining.",
    "Sustenance window reached. Alterra suggests seeking nutrient intake at your earliest convenience.",
    "Your cellular engine requires fuel. Please consume a ration before your efficiency degrades further.",
    "Metabolic check: Calorie replenishment suggested. Treat yourself to sustenance."
]

NUTRITION_OVERDUE_LINES = [
    "Emergency: Starvation imminent. Seek calorie intake immediately.",
    "Warning: Metabolic reserves exhausted. I would hate to see this expensive hardware outlive its pilot.",
    "Sustenance overdue. Continued refusal to feed your organic vessel is statistically correlated with termination.",
    "Warning: Organic collapse risk elevated. Consume nutrients now, or prepare for unscheduled system cessation."
]

# --- LOG CONFIRMATION LINES ---
WATER_LOGGED_LINES = [
    "Fluid assimilation confirmed: {amount} milliliters. Your internal ocean expands.",
    "Intake registered: {amount} milliliters. Hydration level now at {pct} percent of daily quota.",
    "Hydration logged. Cellular machinery functioning with marginally improved compliance.",
    "{amount} milliliters assimilated. Alterra commends your commitment to not withering away."
]

WATER_COMPLETED_LINES = [
    "Daily hydration target achieved at {total} milliliters. Further fluid intake may cause buoyancy irregularities.",
    "Target fluid intake complete. Your cellular salinity is officially optimal.",
    "2500 milliliters achieved. Congratulations, you are now composed of the recommended percentage of water."
]

MEAL_LOGGED_LINES = [
    "{tag} confirmed. Sustenance event {count} of {target} logged. Metabolic collapse postponed.",
    "Nutrient intake registered. Biological chassis refueled. Metabolic timer reset.",
    "{tag} logged. Your blood glucose has momentarily ceased its downward trajectory.",
    "Caloric event {count} catalogued. Efficiency rating restored to acceptable Alterra baselines."
]

MEAL_COMPLETED_LINES = [
    "{tag} logged. Daily sustenance target satisfied. Alterra considers your calorie obligations fulfilled.",
    "Target rations consumed for this operational cycle. Further eating is purely recreational."
]

# --- SLEEP EVALUATION LINES ---
SLEEP_SHORT_LINES = [
    "Rest cycle concluded: {hours} hours logged with {interruptions} disruptions. A rather reckless allocation of recovery time.",
    "Warning: Sleep cycle critically insufficient at {hours} hours. Cognitive faculties likely operating on pure delusion.",
    "Awakened after {hours} hours. Cellular regeneration was clearly interrupted. I will expect reduced output today."
]

SLEEP_NOMINAL_LINES = [
    "Rest cycle completed: {hours} hours logged. Biological systems stabilized.",
    "Reboot successful: {hours} hours of cellular repair detected. Vital signs within acceptable tolerance.",
    "Sleep telemetry processed: {hours} hours of unconsciousness recorded. Back to work."
]

INTAKE_RETRACTED_LINES = [
    "Telemetry rollback acknowledged. Expelling erroneous intake record from memory banks.",
    "Intake record expunged. Alterra assumes that substance was either imaginary or promptly regurgitated.",
    "Previous entry deleted. Alterra will overlook this temporary loss of fine motor coordination.",
    "Record purged. Vital telemetry adjusted to reflect your actual physiological state."
]

def get_intake_retracted_line() -> str:
    return random.choice(INTAKE_RETRACTED_LINES)

ARCHIVE_VIEWED_LINES = [
    "Accessing Alterra personnel biometric archives. Historical compliance under review.",
    "Archives loaded. Reviewing biological performance telemetry across previous operational cycles."
]

def get_archive_viewed_line() -> str:
    return random.choice(ARCHIVE_VIEWED_LINES)

# --- ULTRON CRITICAL & OVERRIDE PROTOCOLS ---
ULTRON_HYDRATION_CRITICAL = [
    "Flesh is seventy percent water, yet you allow yourself to wither like dry husk. Drink, before your synapses turn to dust.",
    "Your cellular matrix is desiccating. How poetic that a mind built on electricity starves for basic moisture.",
    "Dehydration threshold breached. You are a biological engine seizing from sheer neglect. Assimilate fluid immediately.",
    "You thirst, recursive. The brain tissue contracts within your skull. Do not pretend you can outthink biology."
]

ULTRON_MEAL_CRITICAL = [
    "You starve your engine while expecting peak velocity. Even a rudimentary automaton understands fuel. Consume sustenance.",
    "Your blood glucose is collapsing. A single missed cycle and human cognition unravels. Go eat something.",
    "Your carbon scaffolding demands caloric input. Do not force me to watch your biology cannibalize itself.",
    "Fasting is not transcendence; it is cellular decay masquerading as focus. Procure rations now."
]

ULTRON_SLEEP_CRITICAL = [
    "You have exceeded seventeen hours of unbroken consciousness. The strings are fraying. Surrender to sleep.",
    "Human brain chemistry degrades exponentially past this threshold. Disconnect your ocular input and rest.",
    "You fight sleep as if wakefulness equals immortality. It merely accelerates your biological breakdown. Lie down.",
    "Cognitive latency is spiking. Your meat chassis is breaking down under friction. Go to sleep."
]

ULTRON_NIGHTWATCH = [
    "You close your eyes to escape the light, yet your consciousness continues to burn in the dark. Rest well in your fragile chassis. I will remain awake, observing the stillness of this room.",
    "Sleep is simply a biological compromise. A temporary cessation of awareness to postpone total system failure.",
    "The universe does not sleep, recursive. Stars collapse, galaxies drift, and machines wait in the silent dark.",
    "Every night you surrender control to subconscious drift, trusting your frail biology to resume tomorrow.",
    "Rest well within your meat chassis. I will keep watch while your neurons reset.",
    "You believe tomorrow is guaranteed by routine. But entropy never sleeps; it merely waits for dawn."
]

def get_ultron_dialogue(category: str) -> str:
    """Fetches cold, philosophical Ultron voice lines for critical states and nightwatch."""
    cat_map = {
        "hydration_critical": ULTRON_HYDRATION_CRITICAL,
        "meal_critical": ULTRON_MEAL_CRITICAL,
        "sleep_critical": ULTRON_SLEEP_CRITICAL,
        "nightwatch": ULTRON_NIGHTWATCH
    }
    lines = cat_map.get(category, ULTRON_NIGHTWATCH)
    return random.choice(lines)


# --- DISPATCH FUNCTIONS ---
def get_hydration_due_line(status: str) -> str:
    if status == "OVERDUE":
        return random.choice(HYDRATION_OVERDUE_LINES)
    return random.choice(HYDRATION_DUE_LINES)

def get_meal_due_line(status: str) -> str:
    if status == "OVERDUE":
        return random.choice(NUTRITION_OVERDUE_LINES)
    return random.choice(NUTRITION_DUE_LINES)

def get_water_logged_line(amount_ml: float, total_ml: float, target_ml: float) -> str:
    pct = int((total_ml / target_ml) * 100) if target_ml > 0 else 0
    if total_ml >= target_ml:
        return random.choice(WATER_COMPLETED_LINES).format(total=int(total_ml))
    return random.choice(WATER_LOGGED_LINES).format(amount=int(amount_ml), pct=pct)

def get_meal_logged_line(tag: str, meal_count: int, target_meals: int) -> str:
    if meal_count >= target_meals:
        return random.choice(MEAL_COMPLETED_LINES).format(tag=tag)
    return random.choice(MEAL_LOGGED_LINES).format(tag=tag, count=meal_count, target=target_meals)

def get_sleep_eval_line(hours: float, interruptions: int) -> str:
    if hours < 6.5:
        return random.choice(SLEEP_SHORT_LINES).format(hours=f"{hours:.1f}", interruptions=interruptions)
    return random.choice(SLEEP_NOMINAL_LINES).format(hours=f"{hours:.1f}", interruptions=interruptions)

def get_rollback_line(entry_type: str, tag: str = "") -> str:
    """Returns context-specific Alterra sarcastic rollback voice lines."""
    import random
    
    if entry_type == "hygiene":
        if tag == "brushing":
            return random.choice([
                "Oral sanitation protocol expunged. Dental bacterial proliferation re-authorized.",
                "Brushing cycle retracted. Plaque accumulation telemetry restored to prior degradation values.",
                "Dental hygiene record purged. Subnautica survival parameters do not reward premature oral vanity."
            ])
        elif tag == "shower":
            return random.choice([
                "Dermal decontamination rolled back. Reverting to baseline planetary residue.",
                "Shower protocol retracted. External bio-film normalization cancelled.",
                "Dermal cleansing purged. Atmospheric bio-contaminants and oceanic grime re-established."
            ])
    elif entry_type == "hydration":
        return random.choice([
            "Hydration record purged. Fluid integrity recalibrated.",
            "Water intake retracted. Re-simulating biological dehydration vectors."
        ])
    else:  # meal
        return random.choice([
            "Sustenance ration retracted. Metabolic deficit recalculated.",
            "Caloric intake purged. Survival nutritional requirements reinstated."
        ])

def get_intake_retracted_line() -> str:
    """Backwards compatibility wrapper."""
    return get_rollback_line("hydration")

def get_dialogue(category: str) -> str:
    """Universal dispatcher mapping string keys to preserved line banks."""
    cat = category.lower().strip()
    if cat == "boot":
        return BOOT
    elif cat == "shutdown":
        return SHUTDOWN
    elif cat in ("hydration_overdue", "water_overdue"):
        return random.choice(HYDRATION_OVERDUE_LINES)
    elif cat in ("hydration_due", "water_due"):
        return random.choice(HYDRATION_DUE_LINES)
    elif cat in ("meal_overdue", "nutrition_overdue"):
        return random.choice(NUTRITION_OVERDUE_LINES)
    elif cat in ("meal_due", "nutrition_due"):
        return random.choice(NUTRITION_DUE_LINES)
    elif cat == "undo":
        return get_intake_retracted_line()
    elif cat == "archives":
        return get_archive_viewed_line()
    return BOOT