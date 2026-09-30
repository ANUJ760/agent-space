import { describe, it, expect } from "vitest";
import {
  ClientEventSequencer,
  DomainEventPayload,
  VersionedEntity,
} from "@/lib/event-sequencer";

interface TestTask extends VersionedEntity {
  id: string;
  version: number;
  title: string;
  status: "TODO" | "CLAIMED" | "IN_PROGRESS" | "REVIEW" | "DONE" | "BLOCKED";
}

describe("Frontend Live Updates & Stale Event Sequencer", () => {
  const initialTasks: TestTask[] = [
    {
      id: "task-alpha",
      version: 1,
      title: "Alpha Task",
      status: "TODO",
    },
    {
      id: "task-beta",
      version: 2,
      title: "Beta Task",
      status: "CLAIMED",
    },
  ];

  it("applies in-order monotonic live events and updates entity state", () => {
    const sequencer = new ClientEventSequencer<TestTask>(initialTasks);

    const updateEvent: DomainEventPayload<TestTask> = {
      event_id: "evt-1",
      entity_id: "task-alpha",
      entity_type: "TASK",
      version: 2,
      timestamp: new Date().toISOString(),
      data: {
        status: "IN_PROGRESS",
      },
    };

    const applied = sequencer.processEvent(updateEvent);
    expect(applied).toBe(true);

    const task = sequencer.getEntity("task-alpha");
    expect(task).toBeDefined();
    expect(task?.version).toBe(2);
    expect(task?.status).toBe("IN_PROGRESS");
    expect(task?.title).toBe("Alpha Task"); // preserved existing fields
  });

  it("rejects duplicate events with the same version to prevent duplicate mutations", () => {
    const sequencer = new ClientEventSequencer<TestTask>(initialTasks);

    const duplicateEvent: DomainEventPayload<TestTask> = {
      event_id: "evt-dup",
      entity_id: "task-beta",
      entity_type: "TASK",
      version: 2, // task-beta is already at version 2
      timestamp: new Date().toISOString(),
      data: {
        status: "DONE",
      },
    };

    const applied = sequencer.processEvent(duplicateEvent);
    expect(applied).toBe(false);

    const task = sequencer.getEntity("task-beta");
    expect(task?.version).toBe(2);
    expect(task?.status).toBe("CLAIMED"); // Not changed to DONE
  });

  it("rejects stale out-of-order events where event.version < current.version", () => {
    const sequencer = new ClientEventSequencer<TestTask>(initialTasks);

    // First advance to version 4
    const v4Event: DomainEventPayload<TestTask> = {
      event_id: "evt-v4",
      entity_id: "task-alpha",
      entity_type: "TASK",
      version: 4,
      timestamp: new Date().toISOString(),
      data: {
        status: "REVIEW",
      },
    };
    expect(sequencer.processEvent(v4Event)).toBe(true);
    expect(sequencer.getEntity("task-alpha")?.version).toBe(4);

    // Now send stale events with version 2 and version 3
    const v2StaleEvent: DomainEventPayload<TestTask> = {
      event_id: "evt-v2-stale",
      entity_id: "task-alpha",
      entity_type: "TASK",
      version: 2,
      timestamp: new Date().toISOString(),
      data: {
        status: "CLAIMED",
      },
    };
    const v3StaleEvent: DomainEventPayload<TestTask> = {
      event_id: "evt-v3-stale",
      entity_id: "task-alpha",
      entity_type: "TASK",
      version: 3,
      timestamp: new Date().toISOString(),
      data: {
        status: "IN_PROGRESS",
      },
    };

    expect(sequencer.processEvent(v2StaleEvent)).toBe(false);
    expect(sequencer.processEvent(v3StaleEvent)).toBe(false);

    // Verify task state remained strictly at version 4 without regression
    const finalTask = sequencer.getEntity("task-alpha");
    expect(finalTask?.version).toBe(4);
    expect(finalTask?.status).toBe("REVIEW");
  });

  it("handles out-of-order sequence [v1, v4, v2, v3, v5] correctly", () => {
    const sequencer = new ClientEventSequencer<TestTask>([
      { id: "task-seq", version: 1, title: "Sequence Task", status: "TODO" },
    ]);

    const events: DomainEventPayload<TestTask>[] = [
      {
        event_id: "e-4",
        entity_id: "task-seq",
        entity_type: "TASK",
        version: 4,
        timestamp: "2026-09-30T10:00:04Z",
        data: { status: "BLOCKED" },
      },
      {
        event_id: "e-2",
        entity_id: "task-seq",
        entity_type: "TASK",
        version: 2,
        timestamp: "2026-09-30T10:00:02Z",
        data: { status: "CLAIMED" },
      },
      {
        event_id: "e-3",
        entity_id: "task-seq",
        entity_type: "TASK",
        version: 3,
        timestamp: "2026-09-30T10:00:03Z",
        data: { status: "IN_PROGRESS" },
      },
      {
        event_id: "e-5",
        entity_id: "task-seq",
        entity_type: "TASK",
        version: 5,
        timestamp: "2026-09-30T10:00:05Z",
        data: { status: "DONE" },
      },
    ];

    const results = events.map((e) => sequencer.processEvent(e));
    expect(results).toEqual([true, false, false, true]);

    const task = sequencer.getEntity("task-seq");
    expect(task?.version).toBe(5);
    expect(task?.status).toBe("DONE");
  });

  it("supports creation of new entities from live stream events", () => {
    const sequencer = new ClientEventSequencer<TestTask>([]);

    const createEvent: DomainEventPayload<TestTask> = {
      event_id: "evt-create-1",
      entity_id: "task-brand-new",
      entity_type: "TASK",
      version: 1,
      timestamp: new Date().toISOString(),
      data: {
        title: "Discovered Task",
        status: "TODO",
      },
    };

    expect(sequencer.processEvent(createEvent)).toBe(true);

    const newTask = sequencer.getEntity("task-brand-new");
    expect(newTask).toBeDefined();
    expect(newTask?.id).toBe("task-brand-new");
    expect(newTask?.version).toBe(1);
    expect(newTask?.title).toBe("Discovered Task");
  });
});
