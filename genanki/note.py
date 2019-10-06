import re
from cached_property import cached_property

from .card import Card
from .util import guid_for, FRONT_BACK, CLOZE

allany_dict = {'any': any, 'all': all}
cloze_regex = [r"{{[^}]*?cloze:(?:[^}]?:)*(.+?)}}", "<%cloze:(.+?)%>"]
cloze_ref_regex = r"{{c(\d+)::.+?}}"


class Note:
  def __init__(self, model=None, fields=None, sort_field=None, tags=None, guid=None):
    self.model = model
    self.fields = fields
    self.sort_field = sort_field
    self.tags = tags or []
    try:
      self.guid = guid
    except AttributeError:
      # guid was defined as a property
      pass

  @property
  def sort_field(self):
    return self._sort_field or self.fields[0]

  @sort_field.setter
  def sort_field(self, val):
    self._sort_field = val

  def _front_back_cards(self):
    if self.model.model_type != FRONT_BACK:
      raise ValueError("Model type '{}' is not FRONT_BACK ({})".format(self.model.model_type, FRONT_BACK))
    rv = []
    for card_ord, any_or_all, required_field_ords in self.model._req:
      op = allany_dict[any_or_all]
      if op(self.fields[ord_] for ord_ in required_field_ords):
        rv.append(Card(card_ord))
    return rv

  def _cloze_cards(self):
    # returns a Card with unique ord for each unique cloze reference
    if self.model.model_type != CLOZE:
      raise ValueError("Model type '{}' is not CLOZE ({})".format(self.model.model_type, CLOZE))
    card_ords = set()
    # find cloze replacements in first template's qfmt, e.g "{{cloze::Text}}"
    qfmt = self.model.templates[0]['qfmt']
    cloze_replacements = set(re.findall(cloze_regex[0], qfmt) + re.findall(cloze_regex[1], qfmt))
    for field_name in cloze_replacements:
      field_index = next((i for i, f in enumerate(self.model.fields) if f['name'] == field_name), -1)
      field_value = self.fields[field_index] if field_index >= 0 else ""
      # update card_ords with each cloze reference N, e.g. "{{cN::...}}"
      card_ords.update([int(m)-1 for m in re.findall(cloze_ref_regex, field_value) if int(m) > 0])
    if card_ords == {}:
      card_ords = {0}
    return [Card(ord) for ord in card_ords]

  # We use cached_property instead of initializing in the constructor so that the user can set the model after calling
  # __init__ and it'll still work.
  @cached_property
  def cards(self):
    try:
      return self._front_back_cards()
    except ValueError:
      return self._cloze_cards()

  @property
  def guid(self):
    if self._guid is None:
      return guid_for(*self.fields)
    return self._guid

  @guid.setter
  def guid(self, val):
    self._guid = val

  def write_to_db(self, cursor, now_ts, deck_id):
    cursor.execute('INSERT INTO notes VALUES(null,?,?,?,?,?,?,?,?,?,?);', (
        self.guid,                    # guid
        self.model.model_id,          # mid
        now_ts,                       # mod
        -1,                           # usn
        self._format_tags(),          # TODO tags
        self._format_fields(),        # flds
        self.sort_field,              # sfld
        0,                            # csum, can be ignored
        0,                            # flags
        '',                           # data
    ))

    note_id = cursor.lastrowid
    for card in self.cards:
      card.write_to_db(cursor, now_ts, deck_id, note_id)

  def _format_fields(self):
    return '\x1f'.join(self.fields)

  def _format_tags(self):
    return ' ' + ' '.join(self.tags) + ' '
