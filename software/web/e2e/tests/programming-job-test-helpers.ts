import { expect, type Locator, type Page } from "@playwright/test";

export type ProgrammingJobMode = "engineering" | "production";
export type ProgrammingJobField = "target" | "image" | "operations" | "policy";
export type ProgrammingJobAction = "start" | "status" | "abort";
export type ProgrammingJobOperation = "erase" | "program" | "verify" | "read";
export type ProgrammingJobPolicy = "repeat" | "retry" | "stop";

const expectedFields: ProgrammingJobField[] = ["target", "image", "operations", "policy"];
const expectedActions: ProgrammingJobAction[] = ["start", "status", "abort"];
const expectedOperations: ProgrammingJobOperation[] = ["erase", "program", "verify", "read"];
const expectedPolicies: ProgrammingJobPolicy[] = ["repeat", "retry", "stop"];

function modeName(mode: ProgrammingJobMode) {
  return mode === "production" ? "Production" : "Engineering";
}

export function programmingJob(page: Page, mode: ProgrammingJobMode) {
  return page.getByRole("region", {
    name: `${modeName(mode)} Programming Job`,
    exact: true,
  });
}

export function programmingJobField(panel: Locator, field: ProgrammingJobField) {
  return panel.locator(`[data-programming-job-field="${field}"]`);
}

export function programmingJobAction(panel: Locator, action: ProgrammingJobAction) {
  return panel.locator(`[data-programming-job-action="${action}"]`);
}

export function programmingJobOperation(panel: Locator, operation: ProgrammingJobOperation) {
  return panel.locator(`[data-programming-job-operation="${operation}"]`);
}

export function programmingJobPolicy(panel: Locator, policy: ProgrammingJobPolicy) {
  return panel.locator(`[data-programming-job-policy="${policy}"]`);
}

export function programmingJobStatusValue(panel: Locator) {
  return programmingJobAction(panel, "status").locator("b");
}

export async function programmingJobFieldOrder(panel: Locator) {
  return panel.locator(":scope [data-programming-job-fields] > [data-programming-job-field]").evaluateAll(elements =>
    elements.map(element => element.getAttribute("data-programming-job-field")),
  );
}

export async function programmingJobActionOrder(panel: Locator) {
  return panel.locator(":scope [data-programming-job-actions] > [data-programming-job-action]").evaluateAll(elements =>
    elements.map(element => element.getAttribute("data-programming-job-action")),
  );
}

export async function programmingJobOperationOrder(panel: Locator) {
  return panel.locator("[data-programming-job-operation]").evaluateAll(elements =>
    elements.map(element => element.getAttribute("data-programming-job-operation")),
  );
}

export async function programmingJobPolicyOrder(panel: Locator) {
  return panel.locator("[data-programming-job-policy]").evaluateAll(elements =>
    elements.map(element => element.getAttribute("data-programming-job-policy")),
  );
}

export async function expectProgrammingJobContract(panel: Locator) {
  await expect(panel).toBeVisible();
  expect(await programmingJobFieldOrder(panel)).toEqual(expectedFields);
  expect(await programmingJobActionOrder(panel)).toEqual(expectedActions);
  expect(await programmingJobOperationOrder(panel)).toEqual(expectedOperations);
  expect(await programmingJobPolicyOrder(panel)).toEqual(expectedPolicies);

  await expect(programmingJobAction(panel, "start")).toHaveCount(1);
  await expect(programmingJobAction(panel, "status")).toHaveCount(1);
  await expect(programmingJobAction(panel, "abort")).toHaveCount(1);
  await expect(programmingJobAction(panel, "status")).toHaveAttribute("role", "status");
}

export async function programmingJobPresentation(panel: Locator) {
  return panel.evaluate(element => {
    const read = (selector: string) => {
      const target = element.querySelector<HTMLElement>(selector);
      if (!target) throw new Error(`missing ${selector}`);
      const style = getComputedStyle(target);
      return {
        display: style.display,
        minHeight: style.minHeight,
        padding: style.padding,
        borderRadius: style.borderRadius,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        position: style.position,
      };
    };
    return {
      field: read('[data-programming-job-field="target"]'),
      operation: read('[data-programming-job-operation="erase"]'),
      start: read('[data-programming-job-action="start"]'),
      status: read('[data-programming-job-action="status"]'),
      abort: read('[data-programming-job-action="abort"]'),
    };
  });
}

export async function expectProgrammingJobDesktopActionGeometry(panel: Locator) {
  const start = await programmingJobAction(panel, "start").boundingBox();
  const status = await programmingJobAction(panel, "status").boundingBox();
  const abort = await programmingJobAction(panel, "abort").boundingBox();
  for (const box of [start, status, abort]) expect(box).not.toBeNull();

  expect(start!.width).toBeGreaterThan(220);
  expect(status!.width).toBeGreaterThan(start!.width);
  expect(status!.width / start!.width).toBeGreaterThan(1.02);
  expect(status!.width / start!.width).toBeLessThan(1.14);
  expect(Math.abs(start!.width - abort!.width)).toBeLessThanOrEqual(3);
  expect(Math.abs(start!.y - status!.y)).toBeLessThanOrEqual(2);
  expect(Math.abs(status!.y - abort!.y)).toBeLessThanOrEqual(2);
  expect(Math.abs(start!.height - status!.height)).toBeLessThanOrEqual(2);
  expect(Math.abs(status!.height - abort!.height)).toBeLessThanOrEqual(2);
  expect(start!.x + start!.width).toBeLessThan(status!.x);
  expect(status!.x + status!.width).toBeLessThan(abort!.x);
}
