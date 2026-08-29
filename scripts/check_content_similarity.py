from content_similarity import passes_similarity_gate, similarity

previous = [
    "هل سألت نفسك ماذا تفعل لو وقعت على عقد من غير ما تقرأ بند الجزاء؟",
    "لو حصل خلاف مع صاحب العمل، أول حاجة راجع المستندات اللي في إيدك.",
]

assert similarity(previous[0], previous[0]) == 1.0
assert similarity(previous[0], "") == 0.0
assert passes_similarity_gate("موضوع قانوني مختلف تمامًا عن المنشورات السابقة.", previous)
assert not passes_similarity_gate(previous[0], previous)
print("Content similarity gate validation: OK")
