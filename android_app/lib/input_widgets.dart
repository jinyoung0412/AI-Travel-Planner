part of 'input_screen.dart';

class _StepDot extends StatelessWidget {
  final int index;
  final String label;
  final int currentStep;
  final Color themeColor;

  const _StepDot({
    required this.index,
    required this.label,
    required this.currentStep,
    required this.themeColor,
  });

  @override
  Widget build(BuildContext context) {
    final isDone = index < currentStep;
    final isActive = index == currentStep;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          width: 30,
          height: 30,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isDone || isActive ? themeColor : Colors.white,
            border: Border.all(
              color: isDone || isActive ? themeColor : Colors.grey.shade300,
              width: 1.5,
            ),
          ),
          child: Center(
            child: isDone
                ? const Icon(Icons.check, size: 14, color: Colors.white)
                : Text(
                    '${index + 1}',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: isActive ? Colors.white : Colors.grey.shade400,
                    ),
                  ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(
            fontSize: 11,
            color: isActive
                ? themeColor
                : isDone
                ? Colors.grey.shade500
                : Colors.grey.shade400,
            fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ],
    );
  }
}

class _ChoiceRow extends StatelessWidget {
  final List<String> options;
  final String? selected;
  final Color themeColor;
  final void Function(String) onSelect;

  const _ChoiceRow({
    required this.options,
    required this.selected,
    required this.themeColor,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 8,
      children: options
          .map(
            (opt) => _ChoicePill(
              label: opt,
              selected: selected == opt,
              color: themeColor,
              onTap: () => onSelect(opt),
            ),
          )
          .toList(),
    );
  }
}

class _ChoicePill extends StatelessWidget {
  final String label;
  final bool selected;
  final Color color;
  final VoidCallback onTap;
  final IconData? icon;
  const _ChoicePill({
    required this.label,
    required this.selected,
    required this.color,
    required this.onTap,
    this.icon,
  });
  @override
  Widget build(BuildContext context) => ChoiceChip(
    label: Text(label),
    selected: selected,
    onSelected: (_) => onTap(),
    showCheckmark: false,
    avatar: icon == null
        ? null
        : Icon(icon, size: 16, color: selected ? Colors.white : color),
    selectedColor: color,
    backgroundColor: Colors.white,
    side: BorderSide(color: selected ? color : Colors.grey.shade300),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    labelStyle: TextStyle(
      fontSize: 13,
      color: selected ? Colors.white : Colors.grey.shade700,
      fontWeight: selected ? FontWeight.bold : FontWeight.normal,
    ),
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
  );
}

class _TagSection extends StatelessWidget {
  final String title;
  final List<String> tags;
  final Set<String> selectedTags;
  final Color themeColor;
  final String? hint;
  final void Function(String) onToggle;

  const _TagSection({
    required this.title,
    required this.tags,
    required this.selectedTags,
    required this.themeColor,
    required this.onToggle,
    this.hint,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF555555),
                ),
              ),
              if (hint != null) ...[
                const SizedBox(width: 6),
                Text(
                  hint!,
                  style: const TextStyle(
                    fontSize: 11,
                    color: Color(0xFFFF7043),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: tags.map((tag) {
              final sel = selectedTags.contains(tag);
              return _ChoicePill(
                label: tag,
                selected: sel,
                color: themeColor,
                onTap: () => onToggle(tag),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _SlotChip extends StatelessWidget {
  final String slotType;
  final VoidCallback onTap;

  const _SlotChip({required this.slotType, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final style =
        _kSlotStyles[slotType] ??
        const _SlotStyle(Icons.place, Color(0xFF607D8B));
    final icon = style.icon;
    final color = style.color;
    return Semantics(
      button: true,
      label: '활동 $slotType 변경',
      child: InkWell(
        onTap: onTap,
        child: Container(
          width: 76,
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 6),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: color.withValues(alpha: 0.5)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: color, size: 24),
              const SizedBox(height: 7),
              Text(
                slotType,
                style: TextStyle(
                  fontSize: 10,
                  color: color,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
