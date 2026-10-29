import json, re
from pathlib import Path
from sqlalchemy import create_engine, text

meta = json.loads(Path('/tmp/uams-e2e/meta.json').read_text(encoding='utf-8'))
BACKEND_ENV = Path(__file__).resolve().parents[3] / 'backend' / '.env'
url = re.search(r'^DATABASE_URL=(.+)$', BACKEND_ENV.read_text(encoding='utf-8'), re.M).group(1).strip()
url = url.rsplit('/', 1)[0] + '/uams_test?charset=utf8mb4'
eng = create_engine(url)
tc_id = meta['tclass']['id']; stu_id = meta['student']['id']; task_id = meta['task_id']; course_id = meta['course']['id']
with eng.begin() as c:
    assert c.execute(text('SELECT DATABASE()')).scalar() == 'uams_test'
    uid = c.execute(text('SELECT user_id FROM students WHERE id=:i'), {'i': stu_id}).scalar()
    c.execute(text('DELETE FROM grades WHERE teaching_class_id=:t OR student_id=:s'), {'t': tc_id, 's': stu_id})
    c.execute(text('DELETE FROM course_selections WHERE teaching_class_id=:t OR student_id=:s'), {'t': tc_id, 's': stu_id})
    c.execute(text('DELETE FROM schedules WHERE teaching_class_id=:t'), {'t': tc_id})
    c.execute(text('DELETE FROM teaching_classes WHERE id=:i'), {'i': tc_id})
    c.execute(text('DELETE FROM teaching_tasks WHERE id=:i'), {'i': task_id})
    c.execute(text('DELETE FROM courses WHERE id=:i'), {'i': course_id})
    c.execute(text('DELETE FROM students WHERE id=:i'), {'i': stu_id})
    if uid:
        c.execute(text('DELETE FROM user_roles WHERE user_id=:u'), {'u': uid})
        c.execute(text('DELETE FROM users WHERE id=:u'), {'u': uid})
with eng.connect() as c:
    left = {
        'students': c.execute(text("SELECT COUNT(*) FROM students WHERE student_no LIKE 'E2EACC%'")).scalar(),
        'teachers': c.execute(text("SELECT COUNT(*) FROM teachers WHERE teacher_no LIKE 'E2EACC%'")).scalar(),
        'courses': c.execute(text("SELECT COUNT(*) FROM courses WHERE code LIKE 'E2EACC%'")).scalar(),
        'classes': c.execute(text("SELECT COUNT(*) FROM teaching_classes WHERE code LIKE 'E2EACC%'")).scalar(),
        'users': c.execute(text("SELECT COUNT(*) FROM users WHERE username LIKE 'E2EACC%'")).scalar(),
    }
eng.dispose()
print('CLEANUP_OK', left)
