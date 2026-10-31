"""Account verification through the mobile SSO endpoint observed after login."""

from ..exceptions import AuthenticationError
from ..exceptions import ProtocolError
from ..models import Member
from ..transport import Transport


class Account:
    """Read and verify the current account without changing server-side state."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def me(self) -> Member:
        if not self._transport.session.authenticated:
            raise AuthenticationError("A li_at and JSESSIONID session is required.")
        response = await self._transport.request("GET", "/mob/sso/you")
        data = self._transport.json_object(response)
        member_id = data.get("memberID")
        if type(member_id) not in (int, str) or not str(member_id).isdigit():
            raise ProtocolError("Account response did not contain a valid member identity.")
        fields = [data.get(k) for k in ("firstName", "lastName", "fullName", "headline")]
        if not all(isinstance(v, str) for v in fields):
            raise ProtocolError("Account response did not match the captured member schema.")
        state = self._transport.session
        if state.member_id is not None and state.member_id != str(member_id):
            state.clear_authentication()
            self._transport.checkpoint()
            raise AuthenticationError("The session resolved to a different account.")
        state.member_id = str(member_id)
        self._transport.checkpoint()
        return Member(
            str(member_id), data["firstName"], data["lastName"], data["fullName"], data["headline"]
        )
