import unittest

from echo_adventure.decisions import select_echo_choice
from echo_adventure.enums import DecisionType
from echo_adventure.models import DecisionCard, DecisionChoice


class DeterministicDecisionGenerationTests(unittest.TestCase):
    def test_echo_static_choice_reads_full_reachable_tree(self):
        root = DecisionCard(
            id="ROOT",
            day=1,
            type=DecisionType.CRITICAL_PATH,
            title="Root",
            description="Root",
            target_ids=[],
            severity=1,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Looks good now",
                    description="Looks good now",
                    immediate_effects={"type": "echo_recommendation"},
                    risk_effect=0,
                    reschedule_effect=0,
                    next_card_id="CHILD",
                ),
                DecisionChoice(
                    id="2",
                    label="Safer path",
                    description="Safer path",
                    immediate_effects={"type": "echo_recommendation"},
                    risk_effect=1,
                    reschedule_effect=0,
                ),
            ],
        )
        child = DecisionCard(
            id="CHILD",
            day=2,
            type=DecisionType.CRITICAL_PATH,
            title="Child",
            description="Child",
            target_ids=[],
            severity=1,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Grandchild path",
                    description="Grandchild path",
                    immediate_effects={"type": "echo_recommendation"},
                    risk_effect=0,
                    reschedule_effect=0,
                    next_card_id="GRANDCHILD",
                )
            ],
        )
        grandchild = DecisionCard(
            id="GRANDCHILD",
            day=3,
            type=DecisionType.CRITICAL_PATH,
            title="Grandchild",
            description="Grandchild",
            target_ids=[],
            severity=1,
            choices=[
                DecisionChoice(
                    id="1",
                    label="Hidden bad tail",
                    description="Hidden bad tail",
                    immediate_effects={"type": "wait"},
                    risk_effect=10,
                    reschedule_effect=0,
                )
            ],
        )

        graph = {card.id: card for card in (root, child, grandchild)}

        self.assertEqual(select_echo_choice(root, graph).id, "2")


if __name__ == "__main__":
    unittest.main()
