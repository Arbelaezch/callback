// Helpers for the resume content JSON the editor works on.
// Shape: header{name,headline,email,phone,location,links[]}, summary,
// experience[{company,title,location,start,end,bullets[]}],
// projects[{name,link,bullets[]}], education[{school,degree,start,end,details[]}],
// skills[{category,items[]}].

function nonBlank(list) {
  return (list || []).map((s) => s.trim()).filter(Boolean);
}

/**
 * Drop blank lines from every list and drop entries with nothing in them.
 * The editor keeps blank lines while the user is typing; this runs on save.
 */
export function cleanResume(content) {
  const header = content.header || {};
  const withLines = (items, listKey, requiredKey) =>
    (items || [])
      .map((item) => ({ ...item, [listKey]: nonBlank(item[listKey]) }))
      .filter((item) => (item[requiredKey] || '').trim() || item[listKey].length > 0);

  return {
    ...content,
    header: { ...header, links: nonBlank(header.links) },
    experience: withLines(content.experience, 'bullets', 'company'),
    projects: withLines(content.projects, 'bullets', 'name'),
    education: withLines(content.education, 'details', 'school'),
    skills: (content.skills || [])
      .map((group) => ({ ...group, items: nonBlank(group.items) }))
      .filter((group) => group.items.length > 0),
  };
}

export function moveItem(list, index, direction) {
  const target = index + direction;
  if (target < 0 || target >= list.length) return list;
  const next = [...list];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function patchItem(list, index, patch) {
  return list.map((item, i) => (i === index ? { ...item, ...patch } : item));
}
