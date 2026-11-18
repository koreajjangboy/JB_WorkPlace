from jb_workplace.booknarae_api import _looks_logged_out, parse_loans

LIST_HTML = """<html><a href="/logout.do">로그아웃</a>
<table><thead><tr><th>번호</th><th>도서명</th><th>신청일</th><th>대출일</th><th>반납 예정일</th><th>상태</th></tr></thead>
<tbody>
<tr><td>1</td><td>책 A</td><td>2026.11.01</td><td>2026.11.03</td><td>2026.12.03</td><td>대출중</td></tr>
<tr><td>2</td><td>책 B</td><td>2026-10-01</td><td>2026-10-03</td><td>2026-11-02</td><td>반납완료</td></tr>
<tr><td>4</td><td>책 D</td><td>2026.11.05</td><td></td><td></td><td>제공불가</td></tr>
<tr><td>5</td><td>책 E</td><td>2026.10.20</td><td>2026.10.22</td><td>2026.11.21</td><td>택배접수 (반납)</td></tr>
<tr><td>3</td><td>책 C</td><td>2026.11.10</td><td>2026. 11. 12</td><td>2026년 11월 20일</td><td>대출중</td></tr>
</tbody></table></html>"""


def test_parse_loans_sorts_by_due_and_skips_returned():
    loans = parse_loans(LIST_HTML)
    assert loans == [
        {"title": "책 C", "status": "대출중", "lent_on": "2026-11-12", "due_on": "2026-11-20"},
        {"title": "책 A", "status": "대출중", "lent_on": "2026-11-03", "due_on": "2026-12-03"},
    ]


def test_parse_loans_empty_and_missing_table():
    empty = "<table><tr><th>도서명</th><th>반납예정일</th></tr><tr><td colspan=2>내역이 없습니다</td></tr></table>"
    assert parse_loans(empty) == []
    assert parse_loans("<table><tr><td>다른 표</td></tr></table>") is None


def test_logged_out_detection():
    assert _looks_logged_out("https://cn.nld.go.kr/member/login.do", "")
    assert not _looks_logged_out("https://cn.nld.go.kr/list.do", LIST_HTML)
    assert _looks_logged_out("https://cn.nld.go.kr/list.do", '<input type="password" name="pw">')
