/**
 * Event sequencer for handling live updates and rejecting out-of-order or stale events.
 * Guarantees monotonic progression and protects against UI race conditions.
 */
export interface VersionedEntity {
  id: string;
  version: number;
  [key: string]: unknown;
}

export interface DomainEventPayload<T extends VersionedEntity = VersionedEntity> {
  event_id: string;
  entity_id: string;
  entity_type: string;
  version: number;
  timestamp: string;
  data: Partial<T>;
}

export class ClientEventSequencer<T extends VersionedEntity> {
  private entities: Map<string, T> = new Map();
  private maxSeenVersions: Map<string, number> = new Map();

  constructor(initialEntities: T[] = []) {
    this.setEntities(initialEntities);
  }

  public setEntities(entities: T[]): void {
    this.entities.clear();
    for (const entity of entities) {
      this.entities.set(entity.id, entity);
      this.maxSeenVersions.set(entity.id, entity.version);
    }
  }

  public getEntities(): T[] {
    return Array.from(this.entities.values());
  }

  public getEntity(id: string): T | undefined {
    return this.entities.get(id);
  }

  /**
   * Process incoming live event.
   * Rejects stale events where event.version <= current entity version.
   * Returns true if applied, false if rejected as stale or duplicate.
   */
  public processEvent(event: DomainEventPayload<T>): boolean {
    const current = this.entities.get(event.entity_id);
    const lastVersion =
      this.maxSeenVersions.get(event.entity_id) ?? (current ? current.version : 0);

    if (event.version <= lastVersion) {
      // Stale or duplicate event: drop to prevent UI regression
      return false;
    }

    if (!current) {
      // If it's a new entity creation event (version 1)
      if (event.version === 1 && event.data) {
        const newEntity = { ...event.data, id: event.entity_id, version: 1 } as T;
        this.entities.set(event.entity_id, newEntity);
        this.maxSeenVersions.set(event.entity_id, 1);
        return true;
      }
      return false;
    }

    const updated: T = {
      ...current,
      ...event.data,
      id: event.entity_id,
      version: event.version,
    };

    this.entities.set(event.entity_id, updated);
    this.maxSeenVersions.set(event.entity_id, event.version);
    return true;
  }
}
