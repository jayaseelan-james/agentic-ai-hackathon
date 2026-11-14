"""Opt-in real Gemini dialogue check: python -m backend.tests.live_followup."""
import asyncio
import re

from backend.app.schemas import Incident, Vehicle
from backend.app import main
from backend.tests.live_smoke import turn


async def run():
    original_factory = main.get_provider
    def traced_provider():
        provider = original_factory()
        create = provider.create
        async def traced_create(**body):
            response = await create(**body)
            print({'provider_status': response.get('status'), 'step_types': [step.get('type') for step in response.get('steps', [])]}, flush=True)
            return response
        provider.create = traced_create
        return provider
    main.get_provider = traced_provider
    incident = Incident(vehicle=Vehicle(make='Toyota', model='Corolla', year=2020))
    prompts = [
        'I am safely parked. My car shows a yellow tire-pressure warning. Help me figure out the problem.',
        'The light stays steady, never flashes. None of the tires looks flat or damaged. While parked I used a gauge: rear-left is 1.8 bar and the other three are 2.3 bar. The door label says 2.3 bar cold.',
        'I restored the rear-left tire to the door-label pressure yesterday, but it is low again this morning. While parked I can see a nail embedded in that tire tread.',
    ]
    for index, prompt in enumerate(prompts):
        answer = await turn(incident, prompt)
        print(f'Turn {index + 1}: {answer.text}', flush=True)
        assert 'possible causes' not in answer.text.lower()
        assert not re.search(r'^\s*(?:[-*]|\d+[.)])\s', answer.text, re.MULTILINE), 'Expected concise conversational guidance rather than a fault list'
        if index < 2:
            assert answer.text.count('?') == 1, 'Expected one focused follow-up question'
    assert re.search(r'nail|puncture', answer.text, re.IGNORECASE), 'Expected the explanation to narrow to the reported nail/pressure loss'
    assert not re.search(r'confirmed (?:cause|diagnosis)|definitely', answer.text, re.IGNORECASE)
    print('Live guided follow-up check passed.', flush=True)


if __name__ == '__main__':
    asyncio.run(run())
