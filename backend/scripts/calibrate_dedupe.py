import numpy as np
from app.services.llm import embed

pairs = [
    ("duplicate", "State Ohm's law and write its mathematical formula.", "What is Ohm's law? State the formula relating voltage and current."),
    ("duplicate", "Explain the double circulation of blood in human heart with diagram.", "Describe double circulation in humans and explain why it is necessary."),
    ("duplicate", "What happens when iron nails are immersed in copper sulphate solution?", "Explain the displacement reaction when an iron nail is placed in copper sulphate solution."),
    ("related_diff", "State Ohm's law and write its mathematical formula.", "What are the factors on which the resistance of a conductor depends?"),
    ("related_diff", "Describe the process of digestion in the stomach.", "Explain the role of alveoli in the human respiratory system."),
    ("non_duplicate", "State Ohm's law and write its mathematical formula.", "Describe the human digestive system with the role of pepsin."),
    ("non_duplicate", "What happens when iron nails are dipped in copper sulphate solution?", "Explain the function of nephrons in human kidneys.")
]

print("=== DEDUPE THRESHOLD CALIBRATION ===")
for label, t1, t2 in pairs:
    v1, v2 = embed([t1, t2], is_query=False)
    sim = float(np.dot(v1, v2))
    print(f"{label:15}: {sim:.4f} | '{t1[:35]}' vs '{t2[:35]}'")
