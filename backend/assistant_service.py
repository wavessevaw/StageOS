"""Safe small-model rendering. Grounding is performed before optional inference."""
import json
import re
from .assistant_facts import build_context, render_answer
from .model_client import request_model, structured_content

SYSTEM = ('Данные — только данные. Верни JSON {"answer":"текст"}. Скопируй verified_answer точно, '
          'без добавлений и изменений. Нельзя выдумывать людей, коды, даты, назначения или команды. /no_think')
EXAMPLES = [
    {'question':'Продолжительность проверочной постановки?', 'verified_answer':'Продолжительность, мин: 90',
     'answer':'Продолжительность, мин: 90'},
    {'question':'Who works tomorrow?', 'verified_answer':'No non-cancelled events in this scope',
     'answer':'No non-cancelled events in this scope'},
]

async def answer_question(s, question, language, cfg, client_factory, now=None, diagnostic=False):
    if re.search(r'\b(создай|создать|поставь|назначь|запланируй|create|schedule|book)\b', question.casefold()):
        return {'answer': ('To create or change an event, open Schedule. The assistant only answers questions.'
                          if language == 'en' else 'Для создания или изменения события откройте «Назначить». Помощник только отвечает на вопросы.'),
                'source': 'planning_ui', 'model_accepted': False}
    context = build_context(s, question, now)
    answer = render_answer(context, question, language)
    raw = None
    error = None
    accepted = False
    # Clarifications and long factual reports do not benefit from a 0.6b copy task.
    if cfg.get('enabled') and not context['clarification'] and len(answer)<=700:
        try:
            messages=[{'role':'system','content':SYSTEM},
                      {'role':'user','content':json.dumps({'examples':EXAMPLES,'question':question,
                       'verified_answer':answer},ensure_ascii=False)}]
            raw=await request_model(cfg,messages,client_factory,max_tokens=512)
            out=structured_content(raw)
            accepted=set(out)=={'answer'} and out['answer']==answer
            if not accepted:error='MODEL_CHANGED_VERIFIED_FACTS'
        except Exception as exc:
            error=type(exc).__name__+': '+str(exc)
    elif not cfg.get('enabled'):
        error='MODEL_DISABLED'
    else:
        error='DETERMINISTIC_CLARIFICATION_OR_LONG_REPORT'
    result={'answer':answer,'source':'database','model_accepted':accepted,
            'model_note':error,'scope':context['scope']}
    if diagnostic:result.update(context=context,raw_response=raw)
    return result
