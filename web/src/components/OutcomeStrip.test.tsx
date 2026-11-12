import { fireEvent, render, screen } from "@testing-library/react";
import { OutcomeStrip } from "./OutcomeStrip";

describe("OutcomeStrip", () => {
  it("lists only the outcomes that occurred, with counts and shares", () => {
    render(<OutcomeStrip counts={{ correct: 3, not_retrieved: 1, ignored: 0 }} errors={0} />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Correct: 3, Not retrieved: 1");
    expect(screen.getByRole("button", { name: "Correct: 3 (75%)" })).toBeInTheDocument();
    expect(screen.queryByText("In context, ignored")).not.toBeInTheDocument();
  });

  it("selects an outcome and clears it on a second click", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<OutcomeStrip counts={{ correct: 1, ranked_low: 1 }} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /Retrieved, ranked low/ }));
    expect(onSelect).toHaveBeenLastCalledWith("ranked_low");
    rerender(<OutcomeStrip counts={{ correct: 1, ranked_low: 1 }} onSelect={onSelect} selected="ranked_low" />);
    fireEvent.click(screen.getByRole("button", { name: /Retrieved, ranked low/ }));
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("renders nothing for an empty examination", () => {
    const { container } = render(<OutcomeStrip counts={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
